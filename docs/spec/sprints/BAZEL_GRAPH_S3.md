# S3 bazel_graph lane contract: full Bzlmod graph (Rust, Python workers, web), tinyland registry first then BCR

Status: **Phase 1 contract freeze**, 2026-10-07. Lane `bazel_graph`, sprint
`20261007-s3`, branch `sprint/20261007-s3/bazel_graph`, worktree
`.local/sprint3/bazel_graph`. Tracker: Linear TIN-5722 (estate drift: TIN-5716).
Baseline: `f44f962` (full sha recorded in the Phase 2 receipt).
Authority: operator S3 decision "Full Bazel graph (Rust crate, Python workers,
web) with Bzlmod, tinyland registry first then BCR"
(`docs/spec/sprints/20261007-S3.md`), operator P0 stack rule (latest Skeleton
v5 and latest Effect), repository `AGENTS.md`, R-HOOK-CONVERGENCE-20261004
R-N11/R-N12/R-N13. `just` stays the operator entrypoint; Nix stays the dev
environment. Root administers review, signed merge, `just` import, CI,
publication and Linear. This lane never pushes, merges, writes Linear, edits
root-owned files, downloads models, starts a daemon, or requires a remote cache.

No numerics, no Bazel invocation and no `git fetch` were run in Phase 1.
Estate facts in section 3 are a **pre-fetch read of existing remote-tracking
refs**; Phase 2 fetches, re-reads and records the then-current commits. Where
Phase 2 differs, the research doc wins and this section is amended in the same
commit.

## 1. Scope

In scope:

1. **Research record** `docs/research/2026-10-07-estate-bazel-patterns.md`:
   Bazel version, Bzlmod module graph, registry order and URL form, rules
   versions, how estate repos build SvelteKit apps and link registry packages
   (`npm_link_package`), remote-cache configuration; commit and commit date
   per source, sources-state vs lane-infers kept separate.
2. **Bzlmod graph**: `.bazelversion`, `.bazelrc`, `.bazelignore`,
   `MODULE.bazel` (+ `MODULE.bazel.lock` only if Bazel actually resolved it on
   this host; never hand-written), `BUILD.bazel` files for the root crate
   (`src/`, Rust integration tests in `tests/`), `native/au-spike` (Rust
   `staticlib`/`rlib` and its Rust test only), `scripts/` (py_library/
   py_binary), `tests/` (py_test per module) and `web/` (pnpm lock
   translation, SvelteKit check/build targets), plus helpers in `tools/bazel/`.
3. **Registry-module decisions**: one recorded decision per candidate module
   (consume / blocked / not applicable) with evidence (section 5).
4. **Recipes** `just/bazel.just`: `bazel-build`, `bazel-test`, `bazel-graph`;
   the import line is requested from root, not applied by the lane.
5. **Structural test** `tests/test_bazel_graph_s3.py` (section 7).
6. **One bounded host attempt** to run Bazel (section 8) and dated receipts
   under `docs/agent-notes/sprints/20261007-s3/bazel_graph-*.json`.
7. **Root change requests** (text only): `justfile` import line, optional CI
   bazel job, any `.gitignore` line for `bazel-*` symlinks.

Out of scope (not claimed): replacing `just check`/`just test`/
`just test-rust`/`pnpm build` as the accepted gates; remote cache or remote
execution (GloriousFlywheel is reachable only in-cluster); Swift/ObjC/C AU
harnesses, AU packaging, auval or any host acceptance under Bazel; the
optional analysis Python stack (librosa/numpy/torch) as Bazel pip deps; model
downloads; Quarto/R reports; container image builds; publishing video-utils
to any registry; changes to `web/package.json`, `web/pnpm-lock.yaml`,
`Cargo.toml`, `flake.nix`; any DSP, detector, profile, master or listening
claim. The graph changes no signal path, so the 32 Hz/no-high-pass doctrine is
preserved by construction and no audio result is asserted.

## 2. Owned files

| Path | Role |
| --- | --- |
| `docs/spec/sprints/BAZEL_GRAPH_S3.md` | This contract |
| `docs/research/2026-10-07-estate-bazel-patterns.md` | Estate pattern record |
| `.bazelversion`, `.bazelrc`, `.bazelignore` | Version pin, registries, ignored trees (`.local`, `artifacts`, `target`, `web/node_modules`, `web/build`, `web/.svelte-kit`, `data`, `models`) |
| `MODULE.bazel`, `MODULE.bazel.lock` | Module graph; lock only when Bazel-generated |
| `BUILD.bazel` | Root package (exports, aliases) |
| `src/BUILD.bazel` | `rust_library`/`rust_binary`/`rust_test` for crate `video-utils` |
| `tests/BUILD.bazel` | py_test per `tests/test_*.py`; Rust integration tests `cli.rs`, `dsp.rs` |
| `scripts/BUILD.bazel` | py_library/py_binary for `scripts/*.py` |
| `web/BUILD.bazel` | `npm_link_all_packages`, svelte-check and vite build targets, registry `npm_link_package` only for compliant modules |
| `native/au-spike/BUILD.bazel` | `video_utils_gain_ffi` static/rlib + `biquad_ffi.rs` test |
| `tools/bazel/` | Macros (`.bzl`), `coverage_exclusions.json`, `registry_modules.json` |
| `just/bazel.just` | Recipes |
| `tests/test_bazel_graph_s3.py` | Lane test module |
| `docs/agent-notes/sprints/20261007-s3/bazel_graph-*.json` | Dated receipts |

Lane scratch goes only under
`.local/sprint3/bazel_graph/artifacts/s2/bazel_graph/` (gitignored). Root-owned
files are never edited; requested diffs are returned as text.

## 3. Estate sources (remote default branches only)

Pre-fetch remote-tracking refs read in Phase 1 with `git show <ref>:<path>`:

| Repo (remote/branch) | Ref tip, commit date | Read |
| --- | --- | --- |
| tinyland-inc/xoxd.ai `origin/main` | `cc570c3c1079cc5754840395184f0c1a6fece97f`, 2026-10-05 | `.bazelversion`, `.bazelrc`, `MODULE.bazel`, `package.json`, BUILD list |
| tinyland-inc/site.scaffold `origin/main` | `9fef9eea73cb948f984acd8c6159a6422778956a`, 2026-10-05 | same + root `BUILD.bazel` |
| xoxd-ai/tinyland.dev `github/main` | `7422982619e357d31a0ddf0affdf8dedd0b51a93`, 2026-10-02 | same |
| tinyland-inc/bazel-registry `origin/main` | `8d3e5407863132f62c14a5d674435890823a9d22`, 2026-10-05 | `bazel_registry.json`, `modules/` list, `xoxd_spectrogram/0.1.0`, `xoxd_theme/0.1.1`, `xoxd_public_chrome/0.1.0` |

Facts read (sources state):

- **Bazel version.** xoxd.ai and site.scaffold `.bazelversion` `8.2.1`;
  tinyland.dev `8.1.1`.
- **Registry order.** Two `common --registry=` lines, house registry first,
  `https://bcr.bazel.build` second. The house URL is
  `raw.githubusercontent.com/<org>/bazel-registry/<40-hex commit>`, i.e.
  commit-pinned: site.scaffold pins `tinyland-inc/bazel-registry@bdb645c7...`,
  xoxd.ai pins `xoxd-ai/bazel-registry@6d008c19...`. tinyland.dev's
  `.bazelrc` shows only the BCR line in the grep taken (to re-read in full).
- **Rules.** `bazel_skylib 1.8.2` (tinyland.dev `1.9.0`), `platforms 1.0.0`,
  `aspect_bazel_lib 2.22.5`, `rules_pkg 1.1.0`, `rules_nodejs 6.7.3`,
  `aspect_rules_js 2.9.1`, `aspect_rules_ts 3.8.4`, `aspect_rules_swc 2.6.1`;
  tinyland.dev also `rules_python 1.8.3`, `rules_nixpkgs_core 0.13.0`,
  `rules_img 0.3.4`. Node toolchain `22.13.1`, pnpm extension `10.13.1`,
  `npm.npm_translate_lock(pnpm_lock = "//:pnpm-lock.yaml", ...)`, rules_ts
  `ts_version` `6.0.3` (site.scaffold) / `5.9.3` (xoxd.ai). No `rules_rust`
  dep was seen in the three app repos' `MODULE.bazel` grep.
- **Registry package linking.** `bazel_dep(name = "<module>", version = ...)`
  paired with `npm_link_package(name = "node_modules/@scope/pkg",
  src = "@<module>//:pkg")` in the consumer BUILD (site.scaffold root
  `BUILD.bazel`, `TINYLAND_HOUSE_PACKAGES`); first-party packages are not npm
  specifiers. xoxd.ai states its canonical site build is still
  `pnpm run build` with Bazel as the carrier for in-house packages;
  site.scaffold states Bazel targets own build/check/test with Just as entry.
- **Remote cache.** xoxd.ai: disk cache only, "GloriousFlywheel v4 has no
  checked-in remote profile". site.scaffold/tinyland.dev: `--remote_cache`
  supplied explicitly at invocation from validated env, never hard-coded.
- **Estate stack pins (app repos).** xoxd.ai: Skeleton `5.0.1`, effect
  `^3.22.2`, pnpm `10.13.1`. site.scaffold: Skeleton `5.0.1`, effect
  `^3.22.1`. tinyland.dev: Skeleton `^4.15.2`. video-utils: Skeleton `5.0.1`,
  effect `4.0.1`, pnpm `11.25.0`, Node `>=22.12 <23`, TypeScript `6.0.3`.
- **Registry modules** (tinyland-inc/bazel-registry `modules/`): 67 entries
  in the Phase 1 listing, including `xoxd_spectrogram` (versions `0.1.0`),
  `xoxd_theme` (`0.1.0`, `0.1.1`), `xoxd_public_chrome` (`0.1.0`),
  `rules_tectonic`, and 59 `tummycrypt_*` modules. Phase 2 re-counts and
  records the latest version of each.
- **`xoxd_spectrogram` 0.1.0** `MODULE.bazel` docstring says "Svelte 5 +
  Skeleton 5.0.1"; it has `bazel_dep`s on `xoxd_theme 0.1.0`,
  `tummycrypt_tinyland_composables 0.2.4`, `tummycrypt_tinyland_color_utils
  0.2.3`, and its own non-dev `npm_translate_lock`; source is
  `xoxd-ai/xoxd-spectrogram@8264a38651c7...`.

Lane inferences (not source statements): the estate default for a new repo is
Bazel 8.2.1 with the commit-pinned tinyland-inc registry first; a docstring is
not evidence of a module's resolved dependency pins (section 5).

Per the repo-contract skill: first-party packages resolve through
`bazel_dep`/Bzlmod only, never as npm specifiers; the resolution oracle is
`bazel mod graph`/`bazel query`. A text or structural check is **inventory,
not proof of a dependency edge**. video-utils has no `tinyland.repo.json`
manifest; that is reported as UNCOVERED, not created by this lane.

## 4. Frozen design decisions

1. `.bazelversion` = the estate majority value confirmed after fetch
   (expected `8.2.1`).
2. `.bazelrc`: `common --enable_bzlmod`; exactly two `common --registry=`
   lines, the first matching
   `https://raw.githubusercontent.com/tinyland-inc/bazel-registry/<40-hex>`
   (commit = fetched `origin/main` tip, recorded), the second exactly
   `https://bcr.bazel.build`. No `--remote_cache`, `--remote_executor` or
   `--bes_backend` anywhere outside a `try-import %workspace%/user.bazelrc`.
   Disk cache under the user cache dir only. `test --test_env=FFMPEG
   --test_env=FFPROBE` (pass-through, no value in the file).
3. `MODULE.bazel`: `rules_rust` (crate universe not needed: both crates have
   zero external dependencies; toolchain version pinned to `1.95.0`, edition
   `2024`, equal to `rust-toolchain.toml`/`Cargo.toml`), `rules_python`
   (hermetic interpreter `>=3.12` per `pyproject.toml`; no pip hub: workers
   are stdlib-first), `aspect_rules_js` + `aspect_rules_ts` +
   `rules_nodejs` + `aspect_bazel_lib` at estate versions unless BCR
   resolution in Phase 2 forces otherwise (recorded). `rules_rust` and
   `rules_python` versions are chosen in Phase 2 from BCR and recorded with
   the reason; they are **unknown at freeze**.
4. Web: `npm_translate_lock` over `//web:pnpm-lock.yaml` with
   `web/package.json` and `web/pnpm-workspace.yaml` as data. Bazel carries no
   independent npm version pin: the lockfile and `package.json` are the only
   version sites, so Skeleton `5.0.1`/Effect `4.0.1` cannot diverge. Any
   literal npm version that does appear in a Bazel file (pnpm, node,
   TypeScript) must equal `web/package.json`.
5. Python tests: one `py_test` per `tests/test_*.py` (unittest main shim in
   `tools/bazel/`), `imports` reproducing `PYTHONPATH=tests` and the repo
   root as data where tests read `program/`, `docs/`, `scripts/`, `web/`.
   Tags: `requires-ffmpeg` for modules that need FFmpeg/FFprobe;
   `requires-host-tools` (plus `manual` where the default `bazel test //...`
   would otherwise fail without them) for modules needing `node`/`pnpm`/
   `cargo`/`xcrun`/`auval`/network-free host state; `no-sandbox`/`local` only
   with a recorded reason. The classification list is produced in Phase 2 by
   reading each module, not by grep alone.
6. Coverage exclusions live in `tools/bazel/coverage_exclusions.json`:
   `[{"path", "kind": "worker"|"test", "reason"}]`, each reason non-empty.
   `scripts/frozen/*.py` is covered or listed like any other file.
7. `just/bazel.just`: `bazel-build` (`bazel build //...`), `bazel-test`
   (`bazel test //... --test_env=FFMPEG --test_env=FFPROBE`, tag filters
   documented), `bazel-graph` (`bazel mod graph` + structural test). Recipes
   call `bazelisk` if present else `bazel`, and never add a remote cache.
   Requested root import line: `import 'just/bazel.just'` in `justfile`.
8. Existing gates stay authoritative and unmodified. No Bazel output is
   written into the source tree other than the gitignored convenience
   symlinks (ignore line requested from root).

## 5. Registry-module compliance protocol

A registry module is **consumable** only if all hold, with evidence recorded
in `tools/bazel/registry_modules.json` and the research doc:

- its source `package.json` at the `source.json` commit/tarball (read from
  the module's own remote default branch or the pinned archive; never a
  local working tree) declares no `@skeletonlabs/skeleton*` range admitting
  major 4 and no `effect` range admitting major 3, in `dependencies`,
  `peerDependencies` and `devDependencies` that reach `//:pkg`;
- the same holds for every registry module in its transitive `bazel_dep`
  closure (for `xoxd_spectrogram`: `xoxd_theme`,
  `tummycrypt_tinyland_composables`, `tummycrypt_tinyland_color_utils`);
- its peer ranges admit the video-utils pins (Svelte `5.57.1`, Skeleton
  `5.0.1`, Effect `4.0.1`) without changing `web/package.json` or the lock;
- video-utils has a real use for it (no decorative dependency).

Decision values: `consumed`, `blocked_estate_drift_TIN-5716` (pins Skeleton 4
or Effect 3 anywhere in the closure), `blocked_unverifiable` (source not
readable from a remote), `not_applicable` (compliant or not, no use here),
`deferred_needs_root_change` (compliant and useful but needs a
`web/package.json`/lock/source change the lane does not own). Decided per
module for at least: `xoxd_spectrogram`, `xoxd_theme`, `xoxd_public_chrome`,
and each module in their closure; the remaining `tummycrypt_*` modules are
recorded as a counted group `not_evaluated` unless individually examined.
Zero consumed modules is a valid outcome. A module is never consumed on the
strength of a docstring.

## 6. Completion metrics (denominators and claim classes)

Claim classes: **M** measured by the stdlib structural test or a recorded
command; **I** inference; **U** unknown/not verified. No listening claims.

| # | Metric | Denominator | Class |
| --- | --- | --- | --- |
| 1 | Estate sources recorded with remote, commit, commit date | 4 of 4 repos (xoxd.ai, site.scaffold, tinyland.dev, bazel-registry), post-fetch | M |
| 2 | Required graph files present | 11 of 11: `.bazelversion`, `.bazelrc`, `.bazelignore`, `MODULE.bazel`, `BUILD.bazel`, `src/`, `scripts/`, `tests/`, `web/`, `native/au-spike/` `BUILD.bazel`, `just/bazel.just` | M |
| 3 | Registry order: tinyland commit-pinned first, BCR second, no others | 2 of 2 registry lines; 0 remote-cache/executor flags | M |
| 4 | Worker coverage: `scripts/**/*.py` in a target `srcs` or in exclusions with reason | N of N at test time (Phase 1 inventory: 66 top-level + 1 `scripts/frozen`) | M |
| 5 | Test coverage: `tests/test_*.py` in a `py_test` or in exclusions with reason | N of N at test time (Phase 1 inventory: 94) | M |
| 6 | FFmpeg-dependent tests tagged `requires-ffmpeg` | tagged k of the Phase 2 classified list; Phase 1 grep inventory 32 files mention FFmpeg/media (upper-bound inventory, not the list) | M for tags present; I for completeness of the classification |
| 7 | Rust coverage: crate targets for `video-utils` (lib, bin, `tests/cli.rs`, `tests/dsp.rs`) and `video-utils-gain-ffi` (lib, `biquad_ffi.rs`) | 6 of 6 targets; toolchain `1.95.0`/edition `2024` equal to `rust-toolchain.toml`/`Cargo.toml` (2 of 2 crates) | M |
| 8 | House-stack pin identity: Skeleton `5.0.1` (2 packages), Effect `4.0.1` identical in `web/package.json`, lock importer and any Bazel literal; pnpm/Node/TypeScript literals in Bazel equal `package.json` | 3 of 3 packages; every Bazel literal found | M |
| 9 | Registry-module decisions recorded with evidence | at least 3 named candidates + closure, each with decision and source commit; remaining modules counted | M (recorded); I (compliance reading) |
| 10 | Consumed modules pinning Skeleton 4/Effect 3 | 0 of consumed (consumed may be 0) | M against `registry_modules.json`; edge proof U unless `bazel mod graph` ran |
| 11 | Bazel host run | 1 bounded attempt: `ran_ok`, `ran_failed` or `bazel_run_blocked_on_host` with exact error | M |
| 12 | Existing gates unbroken | owned test module passes; `test_web_stack` static checks pass; no root-owned file changed (0 of the root-owned list in `git diff --name-only`) | M; full `just check`/`just test-rust`/`pnpm build` are root's and stay U in lane receipts unless root runs them |
| 13 | Root change requests delivered as text | justfile import, optional CI job, `.gitignore` line: 3 of 3 | M |

Static validation is not a build: if metric 11 is not `ran_ok`, the graph is
reported as **statically validated, build-unverified**, and analysis-time
errors (label typos, rule attribute errors, lock translation failures) remain
possible.

## 7. Test protocol

Module: `tests/test_bazel_graph_s3.py`, stdlib only, no Bazel, network,
FFmpeg, node or pnpm required. Run from the worktree root:

```
PYTHONPATH=tests python3 -m unittest test_bazel_graph_s3 -v
PYTHONPATH=tests python3 -m unittest test_web_stack -v   # directly affected, static part
```

Fixtures: the repository tree itself (`MODULE.bazel`, `.bazelrc`,
`.bazelversion`, `*/BUILD.bazel`, `tools/bazel/*.json`, `web/package.json`,
`web/pnpm-lock.yaml`, `Cargo.toml`, `native/au-spike/Cargo.toml`,
`rust-toolchain.toml`, `pyproject.toml`, `just/bazel.just`). No media, no
seeds. Parsing is a small Starlark-subset reader (call name, string and list
attributes, `glob` expansion against the tree); anything it cannot parse
fails the test rather than being skipped.

Assertions (each maps to a metric):

- files exist (2); `.bazelversion` is a single `X.Y.Z` line;
- `.bazelrc` registry lines and order, commit-pinned first URL, exact BCR
  second, no remote cache/executor/BES flags, `--test_env=FFMPEG`/`FFPROBE`
  pass-through (3);
- `MODULE.bazel` declares `rules_rust`, `rules_python`, `aspect_rules_js`,
  `aspect_rules_ts`, `rules_nodejs`, `aspect_bazel_lib` with literal versions;
  `npm_translate_lock` points at `//web:pnpm-lock.yaml` (8);
- pin identity: `package.json` vs lock importer vs Bazel literals; Rust
  version/edition identity across `rust-toolchain.toml`, both `Cargo.toml`
  and the Bazel toolchain registration (7, 8);
- coverage: set difference of `scripts/**/*.py` and `tests/test_*.py`
  against target `srcs` ∪ exclusions is empty; every exclusion has a reason
  and names an existing file; no file is both covered and excluded (4, 5);
- every module listed in the Phase 2 FFmpeg classification carries
  `requires-ffmpeg` (6);
- every non-rules `bazel_dep` that resolves to the tinyland registry appears
  in `registry_modules.json` with decision `consumed` and no recorded
  Skeleton-4/Effect-3 pin in its closure; every `npm_link_package` `src`
  module has a matching `bazel_dep` (9, 10);
- `just/bazel.just` defines `bazel-build`, `bazel-test`, `bazel-graph` and
  contains no remote-cache flag (2, 3);
- when `MODULE.bazel.lock` exists it is valid JSON; absence is allowed and
  recorded.

Negative self-checks in the same module (temp copies, no tree mutation):
swapped registry order, an added `--remote_cache`, a dropped test target, an
exclusion without reason, and an Effect `3.x` literal must each fail the
corresponding checker.

Optional oracles, used only if already on PATH and recorded either way:
`buildifier --mode=check --lint=warn` (present at `/opt/homebrew/bin` in
Phase 1; not run), `bazel mod graph`.

## 8. Bounded host attempt (not an experiment)

Phase 1 observation: `bazel` and `bazelisk` on PATH are
`tinyland-local-build-guard` wrappers (`--hosts macbook-neo bazel`); the
flake dev shell does not provide Bazel. Whether the guard permits a local
build on this host is **unknown**. Phase 2 makes exactly one attempt, with a
1800 s timeout, on a small target (order of preference: `bazel mod graph`
then `//src:all` or one stdlib `py_test`), no remote cache, one heavy job at
a time. The guard is advisory infrastructure owned elsewhere: it is not
bypassed, reconfigured or signalled. Outcome is recorded verbatim in
`bazel_graph-host-attempt.json`; a refusal, timeout or fetch failure is
`bazel_run_blocked_on_host` and is a valid completion. No retries tuned to
make it pass.

No experiment is run by this lane, so there is no preregistration: there are
no arms, seeds, held-out data or scoring.

## 9. Explicit unknown fields receipts must carry

Each is a key in `bazel_graph-handoff.json` with a value or the literal
`"unknown"` plus reason; none may be omitted:

- `bazel_host_run` (`ran_ok` | `ran_failed` | `bazel_run_blocked_on_host`),
  `bazel_host_error` (verbatim or null), `bazel_version_observed`;
- `module_lock_generated_by_bazel` (bool) and `mod_graph_verified` (bool);
- `registry_commit_pinned`, `registry_reachable_from_host`;
- `rules_rust_version`, `rules_python_version` and their selection evidence;
- `rules_js_supports_pnpm_11_lockfile` (aspect_rules_js `2.9.1` with a pnpm
  `11.25.0` lock and `pnpm-workspace.yaml` settings: unknown until a run);
- `rules_ts_supports_typescript_6_0_3` (site.scaffold precedent is I, not M);
- `rust_1_95_edition_2024_toolchain_available_in_rules_rust`;
- `hermetic_python_used` (bool) and `hermetic_python_version`;
- `ffmpeg_tagged_tests` count and `ffmpeg_classification_method`;
- `host_tool_tagged_tests` count; `excluded_workers`, `excluded_tests` counts;
- `registry_modules` decisions with `not_evaluated` count;
- `dependency_edge_proof` (`bazel_mod_graph` | `structural_inventory_only`);
- `sveltekit_build_under_bazel` (`built` | `declared_unbuilt`);
- `ci_bazel_job` (`requested_not_applied`);
- `repo_manifest_tinyland_repo_json` (`absent_uncovered`);
- `remote_cache` (`not_configured`), `listening_claims` (`none`).

## 10. Receipts

`bazel_graph-contract-freeze.json` (this phase's facts, in Phase 2 with the
post-fetch commits), `bazel_graph-host-attempt.json`,
`bazel_graph-tests.json` (commands, counts, pass/fail),
`bazel_graph-root-requests.json` (exact diffs for `justfile`,
`.github/workflows/ci.yml`, `.gitignore`), `bazel_graph-handoff.json`
(section 9 keys, commit shas, R-N13 citation).
