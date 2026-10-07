# S3 public_site lane contract: static public landing (site.scaffold conventions, xoxd chrome/theme)

Status: **Phase 1 contract freeze**, 2026-10-07. Lane `public_site`, sprint
`20261007-s3`, branch `sprint/20261007-s3/public_site`, worktree
`.local/sprint3/public_site`. Tracker: Linear TIN-5723 (stack drift: TIN-5716).
Baseline: `f44f962ba159e82b0384dd89e95d8a3ba5246267`.
Authority: operator S3 decision "site.scaffold landing (static, xoxd
chrome/theme, no real-take data; Cloudflare Pages)" and the estate P0 stack
rule (`docs/spec/sprints/20261007-S3.md`), repository `AGENTS.md`,
R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13.
Root administers review, signed merge, `just` recipes, publication and Linear.
This lane never pushes, merges, writes Linear, edits root-owned files, starts a
daemon, downloads a model, creates a Cloudflare project, or deploys anything.

No numerics, installs or builds were run in this phase. Every number below that
describes the future site is a target or a denominator definition, not a result.

## 1. Scope

In scope:

1. `site/`: a static SvelteKit site (adapter-static, every route prerendered)
   derived from the site.scaffold public template conventions (section 3), with
   the xoxd public chrome and theme where they are consumable under plain pnpm
   on Skeleton 5.0.1 (section 4), exact dependency pins and a committed
   `site/pnpm-lock.yaml`.
2. Four routes: `/`, `/features`, `/agents`, `/status` (section 5).
3. A public-output leak scan modelled on xoxd.ai's rule file and scanner
   (section 6): `site/scripts/leak-scan-rules.json`, `site/scripts/leak-scan.mjs`.
4. `tests/test_public_site_s3.py` (section 8).
5. A Cloudflare Pages project plan as a document, `site/DEPLOY.md`, and `just`
   recipe text for root in a receipt (section 9). Nothing is applied.
6. Dated receipts `docs/agent-notes/sprints/20261007-s3/public_site-*.json`.

Out of scope, explicitly not claimed: any deploy, Pages project, DNS record,
custom domain or served proof; analytics or telemetry; forms, uploads, contact
transport; any link to or mention of the private app's hostname; any media
(audio, video, stills, spectrograms) or metric derived from the real take; a
Bazel graph for the site (root's Bazel lane owns that); Playwright or a browser
download; a Vitest suite; changes to `web/`, tools, skills, detectors, profiles
or masters; any listening or accuracy claim.

## 2. Owned files

| Path | Role |
| --- | --- |
| `docs/spec/sprints/PUBLIC_SITE_S3.md` | This contract |
| `site/` (all new files) | The site, its vendored first-party carriers, leak scanner, `site/DEPLOY.md`, `site/.gitignore` |
| `tests/test_public_site_s3.py` | Lane tests |
| `docs/agent-notes/sprints/20261007-s3/public_site-*.json` | Receipts |

Generated and gitignored (by `site/.gitignore`): `site/node_modules/`,
`site/.svelte-kit/`, `site/build/`. Scan reports and logs go under
`.local/sprint3/public_site/artifacts/s2/public_site/` (gitignored by the root
`/artifacts/` rule); no file under `site/` names that directory (section 6.3),
so report paths are passed as command-line arguments.

Root-owned files this lane reads and never edits: `program/tools.json`,
`just/workflow.just`, `program/linear.json`, `docs/spec/PROJECT.md`,
`.github/workflows/ci.yml`, the root `.gitignore`. Requested changes are
recorded as exact text in `public_site-root-requests.json` (section 9).

## 3. Estate facts (remote default branches, fetched 2026-10-07)

Read with `git fetch origin` then `git show origin/main:<path>`. Local sibling
working trees are not evidence.

| Repo | `origin/main` | Commit date | Facts used |
| --- | --- | --- | --- |
| site.scaffold | `9fef9eea73cb948f984acd8c6159a6422778956a` | 2026-10-05T21:35:12-04:00 | `public/template/` (package.json 0.1.1, svelte.config.js, vite.config.ts, src/app.css, src/app.html, src/hooks.server.ts, src/routes/+layout.svelte, +layout.ts, +page.svelte, Justfile, .gitignore, .npmrc); `public/chrome/` (`@xoxd/public-chrome` 0.1.0 package.json, README, exports); root `package.json`; `.gitleaks.toml` |
| xoxd.ai | `cc570c3c1079cc5754840395184f0c1a6fece97f` | 2026-10-05T21:35:12-04:00 | `scripts/lib/leak-scan-rules.json`, `scripts/lib/leak-scan.mjs`, `inhouse/README.md`, `package.json`, `src/app.css`, `docs/agent-notes/2026-09-22-public-experience.md`, `.github/workflows/deploy-pages.yml`, `Justfile` |
| bazel-registry | `8d3e5407863132f62c14a5d674435890823a9d22` | 2026-10-05T21:59:29-04:00 | `releases/site-scaffold-public-v0.1.1/plan.json` and `NOTES.md`; `modules/xoxd_public_chrome/0.1.0/source.json`; `modules/xoxd_theme/0.1.1/source.json` |

Stated by those sources:

- Template `site.scaffold.public` 0.1.1: `@skeletonlabs/skeleton` and
  `@skeletonlabs/skeleton-svelte` exactly `5.0.1`; **no `effect` dependency**;
  `@sveltejs/adapter-static ^3.0.10`, `@sveltejs/kit ^2.70.2`, `svelte ^5.56.8`,
  `vite ^8.2.0`, `tailwindcss ^4.3.3`, `typescript 6.0.3`; `pnpm@10.13.1`; node
  `^22.13.0 || >=24 <25`. `svelte.config.js` uses adapter-static with
  `fallback: '404.html'`, `precompress: true`, `strict: false`, prerender
  errors as warnings, runes mode. `src/routes/+layout.ts` is
  `export const prerender = true`. The layout renders a skip link,
  `PublicNavigation`, a `#content` wrapper and `SiteFooter`.
  `src/hooks.server.ts` injects `FOUC_SCRIPT` from `@xoxd/public-chrome/fouc`.
  `app.html` sets `lang="en" data-theme="xoxd" data-mode="dark"`.
- The template resolves `@xoxd/public-chrome`, `@xoxd/theme` and four
  `@tummycrypt/*` packages through Bazel (`npm_link_package`), not npm. Its own
  `just build`/`check` are Bazel targets.
- Release `site-scaffold-public-v0.1.1`: asset
  `site-scaffold-public-0.1.1.tar.gz`, sha256
  `9d834297fbd8103f30758ac58364c59ba628c8b09d6114b093cc68d5a5acf9a4`, 35 files,
  `template_only: true`, scaffold source `3e46b9ede560cddbbfa91eb0157f09b89319c648`,
  theme source `6c2e81a57dc0a71d5fff209b728309492222e50a`, registry commit
  `6d008c192d1ef25f37e747fa1659109bcadb6666`. NOTES state MIT LICENSE/NOTICE and
  the fonts' OFL are included and that source repositories remain private.
- Registry sources: `xoxd_public_chrome-0.1.0.tar.gz` integrity
  `sha256-AdbvlPHa7HAxfWAGDyjRSO58d2eqhbxqyxKJjVs1RJI=`; `xoxd_theme-0.1.1.tar.gz`
  integrity `sha256-DtBiJ/++QAmLQF+M0gNEKptUEdiLEHndOev70ZfVT0U=`; both under
  release `public-frontend-v0.1.1` of `xoxd-ai/bazel-registry`.
- `@xoxd/public-chrome` 0.1.0 peers: `svelte ^5.56.8`, Skeleton `5.0.1` (both
  packages), `@lucide/svelte ^1.28.0`. Exports `PublicNavigation`, `SiteFooter`,
  `ThemePicker`, `SaturnMark`, the `theme` store, `./styles.css`, `./fouc`.
- xoxd.ai consumes the same modules as `file:inhouse/<pkg>` directories that
  `just inhouse-link` materializes from Bazel; "generated carriers, never
  committed copies" (estate ruling N2, one distribution authority).
- Effect: site.scaffold root `package.json` pins `effect ^3.22.1`; xoxd.ai pins
  `effect ^3.22.2`. Both are behind the P0 rule (latest Effect 4.0.1).
- xoxd.ai's rule file has 17 rules plus host, GitHub-URL and mailbox allowlists.
  One of its rules (`plan-private-name`) lists private individuals' names.

Inferred by this lane (not stated by a source):

- Whether the three public release archives download anonymously from this host
  is **unknown** until Phase 2 tries (NOTES claim anonymous access).
- Whether chrome 0.1.0 and theme 0.1.1 compile cleanly outside Bazel with the
  pins in section 4 is **unknown** until Phase 2 runs `check` and `build`.

## 4. Stack contract

### 4.1 Pins (exact, no ranges)

Every specifier in `site/package.json` `dependencies` and `devDependencies` is
either an exact `MAJOR.MINOR.PATCH` version or a `file:vendor/<dir>` path. No
`^`, `~`, `>=`, `*`, `latest`, git or URL specifiers.

| Package | Pin | Source of the choice |
| --- | --- | --- |
| `@skeletonlabs/skeleton` | `5.0.1` | P0 rule; template |
| `@skeletonlabs/skeleton-svelte` | `5.0.1` | P0 rule; template |
| `effect` | **absent** | The template has no Effect; the site has no use for it. If Phase 2 finds a real need, the only admissible pin is `4.0.1` |
| `@sveltejs/adapter-static` | `3.0.10` | Template floor, pinned exact |
| `@sveltejs/kit` | `2.70.3` | Matches `web/package.json` at baseline |
| `@sveltejs/vite-plugin-svelte` | `7.3.1` | Matches `web/` |
| `svelte` | `5.57.1` | Matches `web/`; satisfies chrome peer `^5.56.8` |
| `svelte-check` | `4.7.6` | Matches `web/` |
| `vite` | `8.3.3` | Matches `web/` |
| `tailwindcss`, `@tailwindcss/vite` | `4.3.3` | Matches `web/`; template floor |
| `typescript` | `6.0.3` | Template and `web/` |
| `@types/node` | `22.20.5` | Matches `web/` |
| `@lucide/svelte` | exact version resolved at lock time within chrome peer `^1.28.0` | Only if the chrome is consumed |
| `@fontsource/inter` | exact version resolved at lock time within template `^5.3.0` | Only if the theme is consumed |
| `@xoxd/public-chrome` | `file:vendor/xoxd-public-chrome` (0.1.0) | Section 4.2 |
| `@xoxd/theme` | `file:vendor/xoxd-theme` (0.1.1) | Section 4.2 |

`packageManager` is `pnpm@11.25.0` and `engines.node` is `>=22.13 <23`, matching
the qualified local toolchain and `web/`. The lockfile additionally contains no
`effect@3` entry and no `@skeletonlabs/*` version other than `5.0.1`.

Scripts: `check` = `svelte-kit sync && svelte-check --tsconfig ./tsconfig.json`;
`build` = `vite build`; `leak-scan` = `node scripts/leak-scan.mjs build`. No
`postinstall`, `prepare` or other lifecycle script. `pnpm.onlyBuiltDependencies`
is limited to `@tailwindcss/oxide` and `esbuild` when required.

### 4.2 Chrome and theme consumption ladder (frozen before trying)

The definition of done requires plain `pnpm install --frozen-lockfile`, so the
template's Bazel link is not available to this site. The ladder is tried in
order; the first rung that satisfies its gate is used and recorded in
`public_site-build.json` as `chrome_rung`.

- **Rung A (preferred): verified public archives, vendored.** Fetch
  `xoxd_public_chrome-0.1.0.tar.gz` and `xoxd_theme-0.1.1.tar.gz` from the
  public registry release URLs in section 3 without credentials; verify each
  against the registry integrity value before unpacking; unpack to
  `site/vendor/xoxd-public-chrome/` and `site/vendor/xoxd-theme/` unmodified,
  keeping LICENSE, NOTICE and the font OFL; copy the licensed fonts to
  `site/static/fonts/`; write `site/vendor/PROVENANCE.json` (URL, registry
  integrity, computed sha256, file count, registry commit, fetch date,
  `modified: false`). Gate: integrity matches, and `check` and `build` pass
  with zero edits to vendored files. Only the public archives are a
  distribution source; the private site.scaffold repository tree is never
  copied into this repository.
- **Rung B: local token-only chrome.** If an archive is not anonymously
  fetchable, fails integrity, or does not compile at the pins without edits:
  the site ships a small local header, navigation and footer built from
  Skeleton 5.0.1 components and theme tokens with a Skeleton preset theme, and
  records `xoxd_chrome_consumed: false`, `xoxd_theme_consumed: false` and the
  observed failure verbatim. No vendored file is patched to force rung A.

Rung A is a recorded deviation from estate ruling N2 (xoxd.ai never commits
carrier copies; it materializes them from Bazel). It is taken because this lane
may not add a Bazel graph and the contract requires a pnpm-only build. Root's
Bazel lane can later replace `site/vendor/` with `npm_link_package`.

Template elements deliberately not carried: mdsvex and shiki (no `.svx`
content), `@tummycrypt/vite-plugin-a11y` and `vite-plugin-skeleton-colors`
(Bazel-only modules), `tinyvectors`, eslint/prettier/vitest/playwright/sharp/
svgo/serve/tsx, the Bazel/Nix files and the template Justfile. Each omission is
listed in `public_site-build.json` under `template_deviations`.

### 4.3 Build configuration

- `site/svelte.config.js`: `@sveltejs/adapter-static` with `pages` and `assets`
  `build`, `fallback: '404.html'`, `precompress: false` (compressed twins are
  opaque to the scanner; Pages compresses at the edge), `strict: true`;
  `paths.base` is the empty string; `prerender.handleHttpError`,
  `handleMissingId` and `handleUnseenRoutes` are `'fail'` (stricter than the
  template's warnings); `compilerOptions.runes: true`.
- `site/src/routes/+layout.ts`: `export const prerender = true;` and nothing
  that disables it. No route sets `prerender = false`, `ssr = false`, or
  exports form `actions`. No `+server.ts` endpoint exists.
- `trailingSlash` stays at the SvelteKit default, so the build contains exactly
  `index.html`, `features.html`, `agents.html`, `status.html` and `404.html` at
  the build root.
- No source maps in the build. No service worker. No `static/_redirects`.
- `site/static/_headers` sets `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, a deny-all `Permissions-Policy` and
  `X-Frame-Options: DENY`. A Content-Security-Policy is not set in this lane
  (the pre-paint theme script is inline); `csp_enforced` is carried as `false`.

## 5. Pages and content contract

Site identity uses the repository working title `video-utils`; a public
product name is not decided (`public_product_name: null`).

| Route | Content |
| --- | --- |
| `/` | What it is (local-first restoration and rhythm review of technical-guitar practice takes, turned into a shareable clip with source-timed review data and reproducible processing evidence); the three product axioms from `AGENTS.md` in the repository's own sense; an honest capability list where each item carries a claim class and the unknowns sit beside the capabilities, not on a separate page only |
| `/features` | Three sections: restoration, phrase and timing review, agent tools. Each has a visible "Measured vs unknown" note with at least one measured-or-implemented statement and at least one unknown |
| `/agents` | Typed MCP tools and skills overview generated at build time from `program/tools.json` (section 5.2) |
| `/status` | What is not done: Logic/AU host acceptance, editor (Final Cut/Resolve) import proof, real-take accuracy unknown, plus the items in section 5.3 |

### 5.1 Claim classes

Authored claims live in one registry, `site/src/lib/content/claims.ts`, and
pages render from it. Each entry has `id`, `text`, `claim_class` and the pages
it appears on. The rendered element carries `data-claim-class="<class>"` and,
for unknowns, `data-unknown="<id>"`. Classes (closed set):

| Class | Meaning on the page |
| --- | --- |
| `implemented` | A tool or stage exists in the repository; says nothing about accuracy |
| `measured_synthetic` | Measured on generated synthetic fixtures only; no figure is quoted |
| `inferred` | A hypothesis the software proposes for human review |
| `product_hypothesis` | The underserved-workflow market assertion; overlapping products acknowledged |
| `unverified_listening` | A listening outcome nobody has accepted |
| `not_done` | Work that has not been performed |
| `unknown` | A quantity with no supporting evidence |

Content rules:

- No number derived from the real take or from any run of it appears anywhere.
  The only numerals allowed in authored copy are: "nine-string", "32 Hz"
  (stated as approximate and as instrument context, not a measurement), dates,
  and counts computed at build time from `program/tools.json`.
- The full custom tuning, the capture-context artist references, the recording
  date and the arrangement intent are not published.
- No note-correctness, missed-note, wrong-note or phrase-error verdict is
  described as a capability. Automatic review markers are described as
  hypotheses for review. Stems are described as estimates from a mixture.
- No claim that EQ or restoration recreates an uncaptured fundamental or
  in-room tone; no "recovered original" wording for any estimate.
- The market statement is a hypothesis; the page says that existing products
  cover many individual features and that specialized accuracy on distorted
  low-register guitar is unverified. No competitor is named and no outbound
  link is published (section 6.2), so no dated comparison is quoted in v1.
- Affirmative-only banned phrases in the build (case-insensitive):
  `studio[- ]quality`, `recovered (original )?stem`, `original stem`,
  `best[- ]in[- ]class`, `the only tool`, `no other (tool|product)`, `100%`,
  `guarantee`, `flawless`, `perfect(ly)? accurate`.

### 5.2 `/agents` generation

`site/src/routes/agents/+page.server.ts` reads `../program/tools.json`
relative to the site root with `node:fs` during prerender. No generated copy is
committed. Per tool it emits exactly four fields: `name`, `title`, `intent`,
and `skill_name` (the skill directory name taken from the `skill` path). It
also emits two aggregates: the tool count and counts by
`implementation_status`, so a list that is mostly experimental is not presented
as finished. It never emits `description`, `inputSchema`, `limitations`,
`dependencies`, `agent_workflow`, `evidence_kind`, paths, or instrument context.

Baseline reading (a fact about the input file, sha256
`392cc900ceeeaf3b2ff3f8973f0b1652627058c4abccf4e168e56d8e035094c5`): 40 tools, 40
distinct skills, 36 `experimental` and 4 `available`. Tests read the
denominator from the file at test time and never hardcode 40.

If a tool's `name`, `title` or `intent` would trip a leak rule, the loader does
not rewrite it: it withholds that tool's intent, renders a visible "intent
withheld from the public page" marker, counts it in
`agents_intents_withheld`, and the exact text is sent to root in
`public_site-root-requests.json`. If the file is missing or malformed the build
fails; there is no silent empty page.

### 5.3 Required unknown and not-done statements

Each id below must appear as a `data-unknown` element on the listed page with
copy that states the limit plainly.

| id | Page(s) | Statement |
| --- | --- | --- |
| `real_take_accuracy` | `/`, `/status` | Accuracy on real recordings is unknown |
| `low_register_pitch_accuracy` | `/features`, `/status` | Pitch and note identification on distorted low-register guitar is unverified |
| `note_correctness_verdicts` | `/`, `/status` | No missed-note or wrong-note verdicts; these need an approved reference |
| `listening_acceptance` | `/features`, `/status` | Restoration and tone results are not listening-accepted claims |
| `stem_identity` | `/features` | Stems are optional estimates from a mixture, never recovered originals |
| `bpm_meter_phrase_nullable` | `/features` | BPM, meter, phrase boundaries and onset confidence may be unknown |
| `logic_au_host_acceptance` | `/status` | AU plugin and Logic host acceptance are not done |
| `editor_import_proof` | `/status` | Final Cut and Resolve marker import is unverified |
| `market_hypothesis` | `/`, `/status` | The underserved-workflow claim is a hypothesis |
| `hosted_availability` | `/status` | There is no public hosted service, sign-up or download |

### 5.4 Not on the site

No `<form>`, `<textarea>`, file input, `action=` or `method=` attribute. No
analytics, beacon, tag manager, telemetry, cookie, or third-party script,
stylesheet, font or image origin; fonts are self-hosted. No `<audio>`,
`<video>`, `<iframe>`, `<object>` or `<embed>`. No raster image. The only
client storage is the theme preference the chrome keeps in the browser, and
`/status` says so. Any `<input>` in the build must belong to the chrome's
theme control and is enumerated in the receipt. No authored outbound link:
every authored `href` begins with `/` or `#`.

### 5.5 Accessibility basics

- `html lang="en"`; one `<main>` and exactly one `<h1>` per page; a `<nav>`
  with an accessible name; a `<footer>`; heading levels never skip downward.
- A skip link is the first focusable element and targets an id that exists.
- Every `<a>` and `<button>` has an accessible name; no positive `tabindex`;
  no click handler on a non-interactive element; `aria-current="page"` on the
  active navigation link when the chrome provides it.
- Colour comes from theme tokens: authored files under `site/src/` (excluding
  `site/vendor/`) contain zero colour literals (`#rgb`/`#rrggbb`, `rgb(`,
  `hsl(`, `oklch(`, `oklab(`).
- `svelte-check` reports zero errors and zero warnings, including `a11y_*`.
- Motion: no authored animation; the chrome's own reduced-motion behaviour is
  not re-verified here.

## 6. Leak scan

### 6.1 Implementation

`site/scripts/leak-scan-rules.json` holds the rules; `site/scripts/leak-scan.mjs`
(Node standard library only) is modelled on xoxd.ai `scripts/lib/leak-scan.mjs`
at `cc570c3`: it walks a directory, scans text extensions (`.html .js .mjs .css
.json .svg .txt .md .xml .map` and extensionless files), refuses any `.map`,
`.pdf`, media or archive file in a public build, applies every rule, checks
every outbound host and mailbox against allowlists, prints findings as
`rule-id file:line`, optionally writes a JSON report to a path given by
`--report`, and exits non-zero on any finding. `tests/test_public_site_s3.py`
re-implements the rule application in Python from the same JSON so the source
scan runs without Node; the two must agree on the fixtures in section 8.

### 6.2 Rules

Ported from xoxd.ai with the same intent (15): `secret-pem-block`,
`secret-ssh-key`, `secret-cloud-access-key`, `secret-forge-token`,
`secret-json-web-token`, `secret-assignment`, `kubeconfig-fragment`,
`internal-hostname`, `private-network-address`, `cache-or-executor-endpoint`,
`localhost-reference`, `source-map-or-dev-artifact`,
`developer-filesystem-path`, `internal-tracker-reference`,
`operator-banned-dash`. The two content-authorship rules keep xoxd.ai's
`skipVendorRuntimeChunks` behaviour for `_app/immutable/chunks/`.

Not ported: `plan-private-name` (it enumerates private individuals; copying it
here would itself be a leak) and `unsourced-promise` (superseded by the banned
phrases in section 5.1). No xoxd.ai allowlist entry is copied.

Added for video-utils (9):

| id | Catches |
| --- | --- |
| `real-take-filename` | A Photo Booth style recording name (`Movie on <d>-<d>-<yy>`) |
| `media-file-reference` | A reference to a `.mov .mp4 .m4v .wav .flac .aiff .aac .mp3` file |
| `content-hash-64` | Any 64-hex string (source sha256, artifact digests) |
| `run-identifier` | A run id shaped `YYYYMMDDTHHMMSSZ-<12 hex>` |
| `artifact-path-reference` | A path segment naming the private artifacts, data, models or sprint worktree directories |
| `nix-store-path` | A `/nix/store/` path |
| `analytics-or-beacon` | Known analytics, RUM and tag-manager hosts and snippets |
| `form-or-upload-surface` | `<form`, `<textarea`, `type="file"`, `enctype=`, `method="post"` |
| `private-estate-hostname` | Estate service hostnames under the operator's private zones and any `*.cloudflareaccess.com` or tunnel hostname |

Total: 24 rules. Allowlists start **empty** for mailboxes and for authored
hosts. Hosts that framework code bakes into chunks (for example `svelte.dev`,
`www.w3.org`, `github.com` inside Svelte's own error text) are added one at a
time only when the Phase 2 build actually contains them, each with the file
and a reason in the rule file's comment block, as xoxd.ai does. Any other
deviation needed because framework code trips a rule is recorded the same way
(rule id, file, measured cause); a rule is never weakened for authored content.

Rule patterns are written so the rule file does not match its own rules (for
example a character class in place of a literal separator), and the rule file
gets no scan exemption.

### 6.3 Scan surfaces

- **Build scan** (all 24 rules plus allowlists): every file under `site/build/`.
- **Source scan** (all 24 rules except `operator-banned-dash` and
  `form-or-upload-surface`, which apply to authored `site/src/` only): every
  tracked or untracked file under `site/` except `node_modules/`,
  `.svelte-kit/`, `build/`, `vendor/`, `static/fonts/` and `pnpm-lock.yaml`.
  `site/vendor/` is third-party archive content and is scanned with the nine
  secret, host-path and real-take rules only.
- **Exact-identifier check**: at test time the test reads `source_sha256` from
  `program/demo-arrangement.json`, the real recording's basename, and the names
  of any run directories present in the main checkout, and asserts that none
  occurs in any file under `site/` (including `vendor/` and the lockfile) or in
  `site/build/`. The count of identifiers checked is reported; zero run
  directories found is reported as zero, not as a pass over an unknown set.
- If the private app's hostname or origin in `deploy/cloudflare/*.json` is
  non-null at test time, the test asserts it occurs nowhere under `site/` or
  the build. At baseline those values are `null`, which is reported as
  `private_app_hostname_checked: false`.

## 7. Completion metrics

Claim classes for metrics: **M** measured by a command in this lane on
synthetic or authored inputs; **I** inferred; **U** unknown or not performed.
Every measured metric is reported as numerator/denominator with the command and
exit status in a receipt. None of these is an accuracy, listening or served
claim.

| # | Metric | Target | Class |
| --- | --- | --- | --- |
| M1 | Exact pins: specifiers in `site/package.json` that are exact versions or `file:vendor/` paths | N/N | M |
| M2 | Skeleton pins equal to `5.0.1` | 2/2 in package.json; 0 other Skeleton versions in the lockfile | M |
| M3 | Effect: absent from package.json and lockfile, or exactly `4.0.1` with 0 `effect@3` lock entries | holds | M |
| M4 | Commands exiting 0, run in order from `site/`: `pnpm install --frozen-lockfile`, `pnpm run check`, `pnpm run build` | 3/3 | M |
| M5 | `svelte-check` errors and warnings | 0 and 0 | M |
| M6 | Prerender config assertions (adapter-static, `prerender = true`, no opt-out, no endpoints, no actions) | 5/5 | M |
| M7 | Expected pages present in `site/build/` | 5/5 (`index`, `features`, `agents`, `status`, `404`) | M |
| M8 | Tools rendered on `/agents`: tool names from `program/tools.json` found in built `agents.html` | T/T, T read at test time | M |
| M9 | Forbidden tool fields in built `/agents` (schema property names, limitations text, skill file paths) | 0 occurrences | M |
| M10 | Leak rules with a firing positive fixture and a silent negative fixture, in both the Node scanner and the Python port | 24/24 each, and 48/48 verdict agreement | M |
| M11 | Build scan findings over F scanned files with R rules | 0 findings; F and R reported; unscannable files listed | M |
| M12 | Source scan findings over S scanned files | 0 findings; S reported | M |
| M13 | Exact real-take identifiers found under `site/` or the build | 0 of K identifiers, K reported | M |
| M14 | Required unknown ids present on their pages (section 5.3) | 15/15 page placements | M |
| M15 | Claim elements carrying a class from the closed set | C/C | M |
| M16 | Banned affirmative phrases in built HTML | 0 of 10 patterns | M |
| M17 | Forbidden surfaces in built HTML (forms, textareas, file inputs, media, iframes, third-party origins, authored outbound links) | 0 each; inputs enumerated | M |
| M18 | Accessibility structure checks per page (section 5.5, 8 checks) | 32/32 over 4 pages | M |
| M19 | Authored colour literals under `site/src/` | 0 | M |
| M20 | Chrome/theme rung used and archive integrity matches | rung recorded; 2/2 integrity if rung A | M |
| M21 | Deployment actions performed | 0 (no wrangler run, no project created) | M |
| M22 | WCAG contrast ratios | not measured | U |
| M23 | Keyboard walkthrough in a real browser | optional; `not_performed` unless a receipt exists | U |
| M24 | Template drift items recorded for TIN-5716 | listed, count reported | M |

Valid completion includes rung B, a withheld intent, or a recorded framework
deviation, provided each is reported with its denominator. A failing M4, M11,
M12 or M13 is not completion.

## 8. Test protocol

Module: `tests/test_public_site_s3.py`. Standard library only. Run from the
worktree root:

```
PYTHONPATH=tests python3 -m unittest test_public_site_s3 -v
```

Directly affected modules to run alongside (they walk the repository or read
package manifests): `test_web_stack`, `test_tool_contracts`. The full suite is
root's.

Classes:

1. `SpecAndReceiptTests` (always): this spec exists; receipts present in the
   phase carry every field in section 10 with an allowed value; `site/DEPLOY.md`
   exists and states that deployment needs a separate operator go.
2. `PinTests` (always): M1, M2, M3; `packageManager`; no lifecycle scripts;
   `site/pnpm-lock.yaml` is committed.
3. `PrerenderConfigTests` (always, static text checks): M6; `strict: true`;
   empty `paths.base`; `site/.gitignore` ignores `node_modules/`,
   `.svelte-kit/` and `build/`.
4. `ContentContractTests` (always, on `site/src/`): the four route files exist;
   the claims registry uses only the closed class set; every section 5.3 id is
   defined; no forbidden surface in source; M19.
5. `LeakRuleTests` (always): rule file shape (24 unique ids, each with
   `pattern`, `flags`, `description`); every pattern compiles in Python; the
   rule file does not match itself; M10 for the Python port; M12; M13; the
   no-artifacts-reference assertion over every file under `site/`.
6. `LeakScannerNodeTests` (skipped with a stated reason when `node` is absent):
   runs `site/scripts/leak-scan.mjs` on the same fixtures; M10 agreement.
7. `BuildTests` (skipped with a stated reason unless `node` and `pnpm` are on
   PATH and `site/node_modules/` exists): runs `pnpm run check` then
   `pnpm run build` from `site/` with a 300 s timeout each, never
   `pnpm install`, never with network-dependent flags; then M5, M7, M8, M9,
   M11, M14, M15, M16, M17, M18 on `site/build/`. A stale `site/build/` is
   never trusted: these checks only run on the build the test just produced.

Fixtures: generated in a `tempfile.TemporaryDirectory` per test. For each rule
one positive file and one negative control, with the triggering strings
assembled from fragments at run time so neither the test module nor any
committed file contains a literal that trips a rule. Fixtures are fully
synthetic (invented hostnames under reserved names, zero-filled digests,
placeholder key shapes); no real identifier is used as a positive. No media
fixture exists because the site shows no media. No seeds are needed: nothing is
random.

Subprocess limits: every child has an explicit timeout (Node scanner 60 s;
check and build 300 s each). At most one build runs at a time. The test never
writes outside its temp directory and `site/.svelte-kit`, `site/build`.

## 9. Cloudflare Pages plan and root requests (no deploy)

`site/DEPLOY.md` documents, as a plan only:

- Build inputs: root directory `site`, command
  `pnpm install --frozen-lockfile && pnpm run check && pnpm run build`, output
  `site/build`, Node 22, no environment variables, no secrets at build time.
  The build reads `program/tools.json` from the repository, so a Pages
  git-integration build needs the whole repository checked out; direct upload
  of a locally or CI-built `site/build` is the recommended path, as xoxd.ai
  does with `wrangler pages deploy build`.
- A gate order: install, check, build, leak scan, lane tests, then deploy.
- The unknowns the operator must decide: Pages project name, account,
  production branch, custom domain, whether previews are public, and the
  Wrangler version to pin.
- A statement that creating the project, attaching a domain and deploying are
  outward-facing actions that need a separate operator go, and that no
  credential belongs in the repository.

`public_site-root-requests.json` carries exact text for root, none of it
applied by the lane:

- `just/workflow.just` recipes: `site-install`, `site-check`, `site-build`,
  `site-leak-scan`, `site-test`, and a `site-pages-deploy` recipe whose body
  refuses to run unless an explicit operator-go variable is set.
- A CI step proposal for `.github/workflows/ci.yml`.
- Any `program/tools.json` text that tripped a leak rule (section 5.2).
- Template drift notes for TIN-5716.

## 10. Explicit unknown fields

Receipts (`public_site-build.json`, `public_site-leak-scan.json`,
`public_site-handoff.json`) carry every field below. A field keeps its unknown
value unless a receipt in this lane proves otherwise; none may be dropped.

| Field | Frozen value | Meaning |
| --- | --- | --- |
| `deployed` | `false` | Nothing was deployed |
| `pages_project_name` | `null` | Not chosen |
| `cloudflare_account` | `null` | Not chosen, never recorded here |
| `public_hostname` | `null` | Not chosen |
| `custom_domain` | `null` | Not chosen |
| `wrangler_version` | `null` | Not pinned; Wrangler is not a dependency |
| `served_check` | `"not_performed"` | No request was made to a served site |
| `public_product_name` | `null` | Working title only |
| `private_app_hostname_checked` | `false` | The private hostname is null at baseline |
| `real_take_accuracy` | `"unknown"` | Not measured by this lane; the site says so |
| `low_register_pitch_accuracy` | `"unknown"` | As above |
| `listening_acceptance` | `"not_claimed"` | No listening claim |
| `logic_au_host_acceptance` | `"not_done"` | |
| `editor_import_proof` | `"not_done"` | |
| `market_claim` | `"hypothesis"` | No dated comparison is quoted on the site in v1 |
| `xoxd_chrome_consumed` | `"unknown"` until Phase 2, then `true` or `false` | Section 4.2 |
| `xoxd_theme_consumed` | `"unknown"` until Phase 2, then `true` or `false` | Section 4.2 |
| `archives_anonymously_fetchable` | `"unknown"` until tried | |
| `contrast_ratio_measured` | `false` | Token use is checked; ratios are not |
| `keyboard_walkthrough` | `"not_performed"` | Unless a browser receipt exists |
| `reduced_motion_verified` | `false` | |
| `csp_enforced` | `false` | |
| `bazel_graph` | `"absent"` | Root's Bazel lane |
| `template_archive_verified` | `false` | The template archive sha256 is quoted from the registry plan, not recomputed, unless Phase 2 downloads it |
| `effect_in_site` | `"absent"` | Or `"4.0.1"` |
| `agents_intents_withheld` | integer | Count of tools whose intent was withheld |
| `media_shown` | `0` | No media of any kind |

## 11. Template drift recorded for TIN-5716

From the facts in section 3; not fixed here, sibling repositories are not edited.

1. site.scaffold root `package.json` pins `effect ^3.22.1` (P0 rule: 4.0.1).
2. xoxd.ai `package.json` pins `effect ^3.22.2` (P0 rule: 4.0.1).
3. The public template itself has no Effect dependency, so this site carries no
   Effect pin to upgrade.
4. The public template uses caret ranges; this site pins exact versions.
5. The public template pins `pnpm@10.13.1`; `web/` and this site use
   `pnpm@11.25.0`. Which one is the estate alignment target is root's call.
6. The public template cannot be built without Bazel; a pnpm-only consumer
   must vendor or re-package the first-party modules (section 4.2).

## 12. Experiment and preregistration

This lane runs **no experiment**. There are no arms, seeds, held-out sets or
scores, and nothing is tuned. `preregistered: false`. The only frozen-in-advance
decisions are the consumption ladder (section 4.2), the rule list (section 6.2)
and the metric targets (section 7), all sealed by this commit before any
install or build.

## 13. Phase 2 implementation record (appended 2026-10-07; sections 1 to 12 are unchanged)

Implemented as frozen. Measured results and their denominators are in
`docs/agent-notes/sprints/20261007-s3/public_site-build.json`,
`public_site-leak-scan.json` and `public_site-tests.json`. Nothing was deployed.

Outcome of the two things section 3 left unknown:

- The three public release archives downloaded anonymously (HTTP 200, no
  credentials) and each matched its registry integrity value. The template
  archive sha256 was recomputed and matches the registry plan; the template
  archive itself is not vendored.
- Chrome 0.1.0 and theme 0.1.1 pass `check` and `build` at the section 4 pins
  with zero edits. **Rung A** was used. Per-file digests are in
  `site/vendor/PROVENANCE.json` and the lane test recomputes them.

Lock-time resolutions (section 4.1): `@lucide/svelte` `1.28.0` and
`@fontsource/inter` `5.3.0`, the versions the public template's own lockfile
resolves.

Deviations from the frozen text, each recorded in the build receipt:

1. Package-manager settings live in `site/pnpm-workspace.yaml`, because pnpm 11
   reads them there and not from a `pnpm` key in `package.json`. No dependency
   needed a build-script approval, so no built-dependency list exists.
2. `<main id="content">` is rendered once by the layout, not by each page as in
   the template. The skip link targets it.
3. SvelteKit also writes `agents/__data.json` for the prerendered server load.
   It carries the same four fields per tool and the two aggregates, is scanned
   as text, and is covered by the forbidden-field check (M9).
4. `src/routes/+error.svelte` supplies the not-found text inside the chrome.
5. Section 6.2 anticipated allowlist and framework entries. Three hosts were
   added, each because the build contains it: `www.w3.org` (SVG and XHTML
   namespace identifiers), `svelte.dev` (runtime error links in framework
   chunks) and `scripts.sil.org` (the font licence text). The forge host is
   not allowlisted; two exact font-project URLs inside the published
   `fonts/OFL.txt` pass through `allowedPublicForgeUrls`, the upstream
   exact-URL mechanism with none of its entries.
6. Two rule patterns were narrowed after framework code tripped them, with the
   measured cause in the rule file comment: the file-input alternative of
   `form-or-upload-surface` (Skeleton attribute selectors in the stylesheet)
   and the advertising-host alternative of `analytics-or-beacon` (a component
   library event-name key). Both still fire on authored HTML, and tests assert
   that.
7. The build-surface scanner refuses raster images as well as maps, documents,
   media and archives, because section 5.4 allows no raster image.
8. `engines.node` is `>=22.13 <23` and the `node` on PATH is 22, but this
   host's pnpm 11 runs on its own bundled runtime and prints an unsupported
   engine warning. `engineStrict` is not set, matching `web/`.

Not done in Phase 2 and still unknown: contrast ratios, a browser keyboard
walkthrough, reduced-motion behaviour, a Content-Security-Policy, any served
check, and every deployment decision in section 10.
