# S4 lane L13-site-hygiene: lock-neutral in-house link, privacy-scan guard, STT cache key (2026-10-16)

Authority: operator S4 plan (`docs/spec/sprints/20261015-S4.md`, milestones "S3 hosting and site" and
"Hygiene and peers"); TIN-6577; TIN-6578; R-HOOK-CONVERGENCE-20261004 R-N13. Branch `chore/s4-followups`,
base `origin/main` at `7d78ebe`.

## Findings (measured)

1. The committed `MODULE.bazel.lock` was stale, not machine-dependent. Its `usagesDigest` for the rules_nodejs
   `node` extension was `SWYuC+Gf…`; Bazel 8.2.1 computes `ioe48Yi9…` both locally and, by the same one-line
   rewrite, on the hosted site runner. With the committed lock, locally:
   - `build --nobuild //... --lockfile_mode=error` fails: "The usages of the extension
     '@@rules_nodejs+//nodejs:extensions.bzl%node' have changed";
   - `mod graph --lockfile_mode=error` exits 2;
   - plain `mod graph` (default `--lockfile_mode=update`) rewrites the digest to `ioe48Yi9…` and exits 0.
   The hosted bazel job ran plain `mod graph` first, so its following `--lockfile_mode=error` build checked the
   lock that `mod graph` had just rewritten, not the committed one. That is why the job stayed green while
   `inhouse-link.mjs` (an update-mode build) rewrote the lock on the site runner. The earlier L7/L8 inference
   ("local Bazel configuration") is superseded by this measurement.
2. With the rewritten digest committed, locally: `mod graph --lockfile_mode=error` exits 0,
   `build --nobuild //... --lockfile_mode=error` exits 0, and the in-house link build
   (`@xoxd_public_chrome//:pkg @xoxd_theme//:pkg //site:node_modules/@xoxd/public-chrome
   //site:node_modules/@xoxd/theme`) exits 0 and leaves `MODULE.bazel.lock` byte-identical.
3. `test_v10_privacy_scan` asserted `digests['checked']` whenever the tree was a linked worktree, even when
   neither the worktree nor the main checkout had `artifacts/runs` (the case for this worktree).

## Change

- `MODULE.bazel.lock`: the one `usagesDigest` line above. sha256 `35c29387…3c5d` → `f41f0a38…df69`.
- `.github/workflows/ci.yml`:
  - site job, "Tracked-file drift after the in-house link": any changed tracked file now fails, including
    `MODULE.bazel.lock` (it prints the lock diff first); the warning branch is gone.
  - bazel job, "Module graph and lock" (outside the lane's named step; disclosed): `mod graph` now runs with
    `--lockfile_mode=error`, so no update-mode run rewrites the lock before the check. Without this the bazel
    job would keep passing on a stale lock.
- `site/DEPLOY.md` (outside the owned list; disclosed): the drift row of the CI table states the new rule.
- `tests/test_public_site_s3.py`: `runs_roots_present()` lists the `artifacts/runs` directories that exist (this
  tree, and the main checkout from a linked worktree); `private_run_digests` uses it. `test_v10_privacy_scan` now
  asserts, when any runs root exists, `checked`, one digest root per existing directory and `files_hashed > 0`
  when the roots hold any file; with no runs root it asserts `checked` is false. The scan itself is unchanged.
- `condense/transcribe.py`: `endpoint(url)` gives `scheme://host:port/path` (default port filled in, IPv6
  bracketed); `provenance()` stores that in `stt.json`, never the query. Requests still carry the query.
- `condense/edl.py`: `work/<clip>.pause_asr.json` keeps its flat `{"a-b": text}` shape (the retired tool's
  shape, so the parity check can still compare it by sha256). A sidecar `work/<clip>.pause_asr.key` records
  `{"stt": key, "pause_asr_sha256": …}`, where `key` is `{backend: cli, model: <file name>}` or
  `{backend: http, url: <endpoint>, url_sha256: <sha256 of the full URL>, language}`. The cache is reused only
  when the key matches the configured STT and the cache's sha256; otherwise it is read again. The key is
  loaded only under `evidence = "asr"`, so other evidence modes never validate the http URL.
- `condense/README.md`, `docs/spec/CONDENSE.md` (outside the owned list; disclosed): one sentence each on the key
  and the query-free URL.
- `scripts/BUILD.bazel`: `workers` data adds `//condense:all_files`. Root `BUILD.bazel`: the sub-package comment
  names condense.
- Tests: `condense/tests/test_edl.py::test_the_pause_asr_cache_is_keyed_by_the_speech_to_text` (cli → same →
  http → same → other query → cli → other model → missing key → edited cache); `condense/tests/
  test_transcribe_http.py` provenance cases (4 URLs) and an end-to-end `stt.json` check against the fake service
  with a query URL.

## Behaviour change to note

An existing `pause_asr.json` without a matching `.key` (every work dir made before this change, an archived
cache copied in by hand) is read again once, then keyed. The archived seed script
`docs/agent-notes/2026-10-15-condense-v5-seed-hand.py` copies archived caches and stubs `read()`; re-run on this
tree it would count every pause span as unheard. It is a record of a finished run and is not changed.

## Gates (local)

- `nix develop .#condense -c just condense-lint condense-test`: ruff clean, 33 files formatted, 141 passed
  (before the loopback literal fix below); after it, `condense-lint` clean and `tests/test_edl.py` plus
  `tests/test_transcribe_http.py` 64 passed.
- `tests/test_public_tree.py` and `tests/test_s4b_tool_admission.py`: 16 tests OK (2 skipped).
- `tests/test_bazel_graph_s3.py`: 51 tests OK (1 skipped).
- Bazel 8.2.1 with the new lock: `mod graph --lockfile_mode=error` 0; `build --nobuild //... --lockfile_mode=error`
  0 (this analyses the new `//scripts:workers` data edge); the in-house link build 0; lock sha256 after all
  three still `f41f0a38…df69`.
- In this linked worktree (main checkout without `artifacts/runs`): frozen site install plus
  `inhouse-link.mjs` left no tracked file changed besides this branch's edits; `SiteVerifyBuildTests`
  4 tests OK, `test_v10_privacy_scan` included.
- `just check` (2058 tests): 3 failures and 6 errors, all environment-only. 8 are marked-video tests that
  stop on "No bounded supported installed font found" (the known missing font). The ninth was
  `test_condense_public_surface`: the leak rule flags a loopback IP literal in two new condense tests. They
  now use `localhost` (the module's `HOST`); that test re-run is OK. Hosted CI is the authority.

## Left as notes (not in scope)

- TIN-6578: admitting the `http` STT backend under MCP (today the preflight refuses non-cli backends) needs its
  own admission revision; not decided here.
- TIN-6578: public-tree residue after TIN-6515 (generic temp-folder and non-public store paths in archived
  receipts) is not touched.
