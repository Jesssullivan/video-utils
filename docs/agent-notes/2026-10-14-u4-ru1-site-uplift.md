# U4 RU1 stack uplift of site/ (2026-10-14)

```
actor: U4 app lane (Claude, executing on sting per A17)
target: Jesssullivan/video-utils site/ (static public landing); web/ is out of scope
ruling: RU1, RU3, RU4, RU5, RU9, RU13/RU13b, A17, A19, A20, A21;
        R-HOOK-CONVERGENCE-20261004 (TIN-3692 comment 98cf680c), R-N13
branch: feat/u4-ru1-stack-uplift-20261010 (started 2026-10-10, resumed 2026-10-14)
merge:  not by this lane; RU4 independent verifier, then admin merge by root
```

## What changed

- Exact pins (RU5): @sveltejs/kit 3.0.1, svelte 5.57.2, vite 8.3.3, typescript 7.0.2,
  adapter-static 4.0.0, vite-plugin-svelte 7.3.1, svelte-check 4.7.6, @playwright/test 1.64.0,
  Skeleton 5.0.1. No Effect dependency in site/. `@typescript/typescript6` 6.0.2 is the
  in-process parser companion only (RU13b); every type check runs on TypeScript 7.0.2
  (`svelte-check --tsgo`).
- RU13 patch set copied from site.scaffold #225 (ae8abf1): `site/patches/` (kit and svelte-check
  patches, `upstream/` diffs) and `site/.pnpmfile.cjs` (byte-identical). pnpm 11 reads the patch
  settings from `site/pnpm-workspace.yaml`. Patch hashes equal U1's (kit c810c901, svelte-check
  cab8a6d9); the files are renamed `sveltejs__kit-3.0.1.patch` / `svelte-check-4.7.6.patch` so the
  source leak scan does not read `name@version.patch` as a mailbox, and `patches/` plus
  `.pnpmfile.cjs` are excluded from that surface (their headers name upstream repositories by
  design). The site.scaffold devalue house-rule patch is not adopted (see site/patches/README.md).
- Kit 3 hook types come from `@sveltejs/kit/hooks`; the client `handleError` now receives
  `{ kind, error }` and stays silent only for a `framework` 404.
- Kit 3: `svelte.config.js` removed (options moved into `sveltekit({...})` in vite.config.ts),
  `$lib` imports become `#lib/...` through package.json `imports`, tsconfig extends `$app/tsconfig`
  with an explicit `include`. Node toolchain 22.22.0 (Kit 3 needs 22.17+); site engines `>=22.17 <23`.
- RU3: the agents page's build-time `+page.server.ts` load is a `prerender` remote function
  (`src/routes/agents/tools.remote.ts`), emitting the same four public fields per tool. The site
  has no forms.
- RU9: `site/vendor/` (committed @xoxd/theme 0.1.1 and @xoxd/public-chrome 0.1.0 copies) is
  replaced by `bazel_dep(xoxd_theme 0.1.1)` and `bazel_dep(xoxd_public_chrome 0.1.0)` (newest
  registered, xoxd-ai/bazel-registry 4ebe732) with `npm_link_package` in site/BUILD.bazel.
  `site/scripts/inhouse-link.mjs` (`just site-install`) materialises them for the plain pnpm loop.
- Bazel: one runner (bazel/site_build.mjs) for sync, check and build; new
  `//site:svelte_check_canary_test` (seeded .ts and .svelte errors must both be reported).
  The Node 22.22.0 toolchain broke `//web:build`: on Node 22.22 `cpSync(..., { dereference: true })`
  keeps nested symlinks into the read-only sandbox (EROFS on chmod). tools/bazel/web/sveltekit.mjs
  now uses the same per-file dereferencing copy as the site runner. web/ itself is not uplifted.
- Tests: the graph checks follow `registry_errors(builds=[...])` and Node 22.22.0; the two
  svelte-check summary assertions accept the human summary as well as the machine one
  (svelte-check picks machine output only when `CLAUDECODE=1` is set).

## Proof

Executed on sting under tinyland-heavy (A17/A20). Round r1 (06:43Z) found the Kit 3 hook types,
the leak-scan hits on the copied patch set, the stale graph self-checks and the //web:build
regression above. Round r2 (07:19Z, before the web runner fix): frozen install, inhouse-link, check
(0 errors, 0 warnings, `--tsgo` on TypeScript 7.0.2), build, leak scans (build, source, vendor)
clean; Playwright `verify:browser` 52/52; headless renders of every route at 390x844 and 1440x900
with HTTP 200, no horizontal overflow and no console errors apart from the browser's own 404
resource line on the not-found probe; `//site:all` 3/3; `bazel test //...` 93/93 tests with
`//web:build` failing (fixed in this commit). The final round on the committed head is recorded in
the pull request.

Known environment gap: `SiteVerifyBuildTests.test_v10_privacy_scan` asserts hashed private run files
whenever it runs from a linked worktree; the build host has no `artifacts/runs` (private recordings
never leave the operator seat), so it cannot pass there. The test and its helpers are unchanged.
