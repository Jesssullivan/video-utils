# S3 bazel_full lane contract: every Python test module run under Bazel, //site, hosted Bazel job proposal

Status: **Phase 1 contract freeze**, 2026-10-07. Lane `bazel_full`, sprint
`20261007-s3`, branch `sprint/20261007-s3/bazel_full`, worktree
`.local/sprint3/bazel_full`. Tracker: Linear TIN-5722 (estate drift: TIN-5716).
Baseline: `549a14dea88f6b7951a81f2c2fa0718cb83a1c21` (main at lane start).
Authority: operator S3 decision "Full Bazel graph (Rust crate, Python workers,
web) with Bzlmod, tinyland registry first then BCR"
(`docs/spec/sprints/20261007-S3.md`), operator P0 stack rule (latest Skeleton
v5 5.0.1 and Effect 4.0.1 only), repository `AGENTS.md`,
R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13 (TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`).

This lane continues `docs/spec/sprints/BAZEL_GRAPH_S3.md` (bazel_graph, merged)
and its receipts `docs/agent-notes/sprints/20261007-s3/bazel_graph-*.json`. It
does not reopen that lane's frozen decisions (Bazel 8.2.1, Bzlmod, commit-pinned
tinyland registry first then BCR, rules versions, no remote cache, zero
registry modules consumed, `no-sandbox` unittest targets, glob-driven coverage).

`just` stays the operator entrypoint and Nix stays the dev environment. `just
check`, `just test`, `just test-rust`, `pnpm build` (web) and `just site-check`
/ `just site-build` stay the accepted gates. Nothing in this lane claims that
Bazel replaces them. Root administers review, signed merge, CI, publication and
Linear. This lane never pushes, merges, writes Linear, edits root-owned files,
downloads models or FFmpeg, starts a daemon, or configures a remote cache.

No numerics, no Bazel invocation and no unittest run were made in Phase 1. The
facts in section 3 come from reading the tree at the baseline and the receipts
named there.

## 1. Scope

In scope:

1. **Full Python coverage under Bazel, executed.** Every `tests/test_*.py`
   module has a `py_test` target (already true by glob; re-proved at the
   Phase 2 head) and **one full `bazel test //...` run** from this worktree is
   executed and recorded per target, with FFmpeg-tagged modules run against
   the Nix FFmpeg through the test environment (section 6).
2. **Known host-specific failures named exactly**, each with evidence that the
   same case also fails under plain `python3 -m unittest` on this host
   (section 7). They are not skipped, not marked expected-failure, not tagged
   `manual`, and not removed from `//...`.
3. **The `.local` path investigation** for the calibration-evaluator cases
   (section 8). If it is a product defect, the result is a root request with a
   minimal fix diff against `scripts/`, never an edit by this lane.
4. **`//site` Bazel targets** for type-check and build, by the `//web` pattern
   (rules_js over `site/pnpm-lock.yaml`), passing (section 9).
5. **A proposed hosted CI job** running `bazel test //...` or a justified
   subset, delivered as a diff against `.github/workflows/ci.yml` in a root
   request, with expected runtime and cache notes (section 10).
6. **Module graph and lock consistency** (`bazel mod graph`,
   `--lockfile_mode=error`), with every new module, extension repository and
   network fetch recorded and justified (section 11).
7. Structural test extension `tests/test_bazel_graph_s3.py` (section 12) and
   dated receipts (section 14).

Out of scope (not claimed): replacing any accepted gate; remote cache or
remote execution; AU/Swift/ObjC/C harnesses or auval under Bazel; the optional
analysis Python stack (librosa/numpy/torch) as Bazel pip deps; model
downloads; Quarto/R; container images; deploying the site; changes to
`web/package.json`, `web/pnpm-lock.yaml`, `site/package.json`,
`site/pnpm-lock.yaml`, `site/vendor/**`, `Cargo.toml`, `flake.nix`; any DSP,
detector, profile, master or listening claim. The graph changes no signal
path: the ~32 Hz / no-blanket-high-pass / no-mains-notch doctrine is preserved
by construction and no audio result is asserted. The lane adopts no default
detector, profile or master.

## 2. Owned files

| Path | Role |
| --- | --- |
| `docs/spec/sprints/BAZEL_FULL_S3.md` | This contract |
| `MODULE.bazel`, `MODULE.bazel.lock` | Module graph; lock only as written by Bazel, never by hand |
| `.bazelrc`, `.bazelversion` | Run configuration (version stays `8.2.1`) |
| `BUILD.bazel`, `**/BUILD.bazel` | Root package and every package file, including the new `site/BUILD.bazel`. `site/vendor/**/BUILD.bazel` are vendored, provenance-bound copies (`site/vendor/PROVENANCE.json`: "Do not edit") and are **not** edited even though the glob matches them |
| `bazel/` | New lane helpers (macros, the classification supplement, the known-host-failure register, the CI job draft) |
| `just/bazel.just` | Recipes (`bazel-site`, a full-run recipe if needed) |
| `tests/test_bazel_graph_s3.py` | Structural test, extended |
| `docs/agent-notes/sprints/20261007-s3/bazel_full-*.json` | Dated receipts |

**Ownership note (recorded, not self-expanded).** The lane list names `bazel/`;
the bazel_graph helpers live in `tools/bazel/` (`python.bzl`, `rust.bzl`,
`run.py`, `unittest_main.py`, `web/sveltekit.mjs`, `test_classification.json`,
`registry_modules.json`, `coverage_exclusions.json`, `ci-bazel-job.draft.yml`).
The lane reads `bazel/` literally: `tools/bazel/*` is reused read-only (by
label or by import), new helpers go under a top-level `bazel/`, and any needed
change to `tools/bazel/*` is returned as an exact diff in
`root_owned_changes_requested`. If root confirms that `bazel/` meant
`tools/bazel/`, the lane applies those diffs itself and records the
confirmation in the handoff. Classification of modules added since the
bazel_graph classification (95 modules then, 98 now) goes into an owned
supplement `bazel/test_classification_s3_full.json`; the structural test checks
`tests/BUILD.bazel` lists against the union of the two files.

Not owned and never edited: `.bazelignore`, `.gitignore`, `justfile`,
`.github/workflows/ci.yml`, `web/**` and `site/**` except their `BUILD.bazel`,
`scripts/**`, every other `tests/*.py`, and the root-owned list
(`scripts/tool_api.py`, `program/tools.json`, `just/workflow.just`,
`scripts/review_server.py`, `scripts/mcp_server.py`, `program/models.json`,
`program/linear.json`, `docs/spec/PROJECT.md`). Lane outputs (logs, parsed
per-target tables, control copies' results) go only under
`.local/sprint3/bazel_full/artifacts/s2/bazel_full/` (gitignored). Accepted
run directories under `artifacts/runs/*` are read-only.

## 3. Facts at freeze (read from the tree and receipts; Phase 2 re-measures)

- `tests/test_*.py`: **98 files** at the baseline (bazel_graph classified 95;
  added since include `test_public_site_s3`, `test_web_house_stack_s3`,
  `test_s3_tool_admission`; exact set re-derived in Phase 2).
- `tests/BUILD.bazel` covers `glob(["test_*.py"])` through
  `//tools/bazel:python.bzl%unittest_py_tests`; classes: `FFMPEG_TESTS` 18,
  `HOST_TOOL_TESTS` 14, `EXCLUSIVE_TESTS` 6, `WORKSPACE_ARTIFACT_TESTS` 26,
  `WEB_TREE_TESTS` 7; `manual` 0; every unittest target `no-sandbox`.
- Rust test targets: 5 (`//:rust_tests`). Web: `//web:svelte_check_test`
  (test), `//web:sveltekit_types`, `//web:build`.
- `web/pnpm-workspace.yaml` now carries `allowBuilds: {}` (the bazel_graph
  root request landed). `site/pnpm-workspace.yaml` does **not** carry
  `allowBuilds`.
- `.bazelignore` already ignores `site/vendor`, `site/node_modules`,
  `site/build`, `site/.svelte-kit` (root commit `8533e9f`).
- `site/` is its own pnpm 11.25.0 workspace (`site/pnpm-lock.yaml`, lockfile
  v9) with Skeleton 5.0.1 (two packages), Svelte 5.57.1, SvelteKit 2.70.3,
  adapter-static 3.0.10, TypeScript 6.0.3, Vite 8.3.3, and no Effect. Two
  dependencies are `file:vendor/xoxd-theme` (0.1.1) and
  `file:vendor/xoxd-public-chrome` (0.1.0), lock resolution
  `{directory: vendor/..., type: directory}`. Both vendored directories carry
  their own `MODULE.bazel` (`xoxd_theme` 0.1.1, `xoxd_public_chrome` 0.1.0,
  each depending on `aspect_rules_js 2.9.1`, `aspect_bazel_lib 2.22.5`) and
  are integrity-verified copies of the public release archives.
- Root reading on TIN-5722 (relayed by the lane brief; not re-measured here):
  Bazel 8.2.1 on neo; Rust 5/5; `//web` type-check and build pass; **74 of 97**
  Python modules ran under Bazel (70 pass, 4 fail on cases that also fail
  under direct unittest only inside a `.local` worktree path: 5
  calibration-evaluator tests error when the path contains `.local`, and 2
  macOS process-inspection tests fail at baseline `a16d02d` on this host);
  the other 23 modules need FFmpeg or host tools and were not run.
- Static leads for section 8 (inference, not yet a finding):
  `scripts/calibration_pilot.py` confines paths beneath `artifacts/benchmarks`
  and invokes evaluator workers; several workers and `scripts/tool_api.py`
  refuse any path component starting with `.`; root's integration receipt
  (`root_integration_g-receipt.json`) records an `apply_capture_profile` real
  render that "skips here by design (worktree path has a dot-prefixed
  component)". Candidate process-inspection cases read `/bin/ps` output
  (`tests/test_apply_capture_profile.py`), unconfirmed.
- Host: shared macOS arm64 (6 CPUs, 8 GiB); 1-minute load **53.4** when read
  at freeze (above the gate in section 6.4).

## 4. Frozen design decisions

1. **No change to the frozen bazel_graph graph** except: the new `//site`
   package, a second `npm_translate_lock` for `site/pnpm-lock.yaml`, the
   classification supplement for new modules, and whatever section 9.3 selects
   for the vendored carriers. Any further change is recorded with its cause.
2. **Known host failures stay visible.** No case-level skip, `expectedFailure`,
   env-var opt-out, `manual` tag, tag filter in the default config, or
   exclusion list is added to make `bazel test //...` green on this host. The
   full run may therefore exit non-zero; that is a valid, recorded outcome.
   Failures are explained in `bazel/known_host_failures.json` (schema in
   section 7) and the receipts, not suppressed.
3. **FFmpeg by environment only.** The Nix store paths are passed at
   invocation (`--test_env=FFMPEG=<path> --test_env=FFPROBE=<path>`), never
   written into `.bazelrc`, `MODULE.bazel` or a `BUILD.bazel`. No FFmpeg is
   downloaded or wrapped as a repository rule.
4. **Host tools by config.** The full run uses the existing
   `--config=host-tools` (PATH, HOME) so host-tool-tagged modules run rather
   than skip; tests still never run `pnpm install` online
   (`test_web_stack` uses `--offline`; `test_public_site_s3` never installs).
5. **`//site` mirrors `//web`**: `npm_link_all_packages`, a copy of the shared
   runner `//tools/bazel:web/sveltekit.mjs` (reused by label, not edited),
   `js_run_binary` sync, `js_test` `svelte_check_test`, `js_run_binary` build
   into a declared `out_dirs`. Optional extra: `//site:leak_scan_test` running
   `site/scripts/leak-scan.mjs` over the Bazel build output (counted separately;
   not required for done).
6. **No in-tree outputs.** Bazel writes nothing into `site/` or `web/`
   (`.svelte-kit`, `build`, `node_modules` stay `pnpm`'s). `site/BUILD.bazel`
   contains no private-tree reference (`artifacts/`, `.local/sprint`, recording
   names, run ids), because `test_public_site_s3` scans every site file.
7. **Bounded execution.** Every Bazel command goes through
   `tools/bazel/run.py` (bounded, refuses remote flags, shuts the server down)
   with `--jobs=4 --local_resources=cpu=4`; `.bazelrc` keeps
   `--local_test_jobs=2`. One heavy job at a time; no concurrent unittest or
   FFmpeg work while Bazel runs.

## 5. Completion metrics (denominators and claim classes)

Claim classes: **M** measured by a recorded command or the stdlib structural
test; **I** inference; **U** unknown/not verified. No listening claims.

| # | Metric | Denominator | Class |
| --- | --- | --- | --- |
| 1 | Python module coverage: `tests/test_*.py` with a `py_test` target, from `bazel query 'kind(py_test, //tests:all)'` and the structural test | P of P, P = file count at the Phase 2 head (98 at freeze); 0 excluded | M |
| 2 | Full `bazel test //...` executed once from the worktree, exit code and wall-clock recorded | 1 of 1 run; `ran_complete` / `ran_timeout` / `blocked_on_host` | M |
| 3 | Per-target outcome of that run | T of T test targets, T = `bazel query 'tests(//...)'` count (expected P + 5 Rust + 1 web + 1 or 2 site); each `PASSED` / `FAILED` / `TIMEOUT` / `FLAKY` / `NO STATUS` / `SKIPPED` with reason | M |
| 4 | Per-module unittest counts parsed from each Python `test.log` | P of P modules with `ran`, `skipped`, `failures`, `errors`, `expected_failures`; skip reasons verbatim | M |
| 5 | FFmpeg-tagged modules run with the Nix FFmpeg | F of F (`requires-ffmpeg` count at head, 18 at freeze + supplement); per module: FFmpeg cases ran vs skipped (a module whose FFmpeg cases all skipped counts as not run) | M |
| 6 | Known host-specific failing cases named exactly (`module.Class.test`) | K of K failing cases in the full run; each with a plain-unittest reproduction on this host (same worktree), and for the `.local` class a control run from a dot-free path | M |
| 7 | Unexplained failures | U_f of failing cases with no reproduction or cause; target 0, any nonzero value reported, not hidden | M |
| 8 | `.local` investigation verdict | 1 of 1: `product_defect` (with minimal fix diff in root request) / `test_fixture_assumption` / `intended_refusal` / `undetermined`, with the exact raising line | M for the raising line; I for the classification rationale |
| 9 | `//site` targets | `//site:svelte_check_test` PASSED and `//site:build` built: 2 of 2 (plus optional leak-scan test, separate) | M |
| 10 | Site build parity | Bazel `//site:build` output file list vs `pnpm run build` output (only if `site/build` already exists; the lane never runs `pnpm install`): `equal` / `differs` with diff / `not_compared` | M or U |
| 11 | Module graph and lock | `bazel mod graph` exit 0 and `bazel build --nobuild //... --lockfile_mode=error` exit 0 at the final head: 2 of 2 | M |
| 12 | New modules and fetches | every `bazel_dep` / `local_path_override` / extension repo added vs baseline listed with reason; Bzlmod registries used 2 of 2 pinned, 0 others; npm archives fetched for `//site` counted (n archives, bytes) and each integrity-bound by `site/pnpm-lock.yaml` | M |
| 13 | House-stack pins under `//site` | Skeleton 5.0.1 (2 packages), no Effect (or exactly 4.0.1), TypeScript/pnpm/Node literals equal `site/package.json`; registry modules pinning Skeleton 4 / Effect 3 consumed: 0 | M |
| 14 | Hosted CI proposal delivered as text | 1 of 1 diff against `.github/workflows/ci.yml` in `bazel_full-root-requests.json`, with expected runtime (I) and cache notes | M (delivered); I (runtime) |
| 15 | Existing gates unbroken | `test_bazel_graph_s3` and `test_public_site_s3` (static part) pass; root-owned files in `git diff --name-only <baseline>`: 0 | M; `just check` / full unittest / `pnpm build` stay U (root runs them) |

Static validation is not a run: if metric 2 is not `ran_complete`, every
target without a recorded status is reported **`not_run`**, never inferred.

## 6. Test protocol (exact)

### 6.1 Lane-owned and directly affected modules (plain unittest)

From the worktree root:

```
PYTHONPATH=tests python3 -m unittest test_bazel_graph_s3 -v
PYTHONPATH=tests python3 -m unittest test_public_site_s3 -v   # site/BUILD.bazel is a new site file
PYTHONPATH=tests python3 -m unittest test_web_stack -v        # static part; //web untouched
```

Fixtures: the repository tree (`MODULE.bazel`, `MODULE.bazel.lock`,
`.bazelrc`, `*/BUILD.bazel`, `tools/bazel/*.json`, `bazel/*.json`,
`site/package.json`, `site/pnpm-lock.yaml`, `site/pnpm-workspace.yaml`,
`web/package.json`, `web/pnpm-lock.yaml`, `just/bazel.just`). No media, no
seeds, no network.

### 6.2 Environment for every Bazel run

```
export FFMPEG=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg
export FFPROBE=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffprobe
uptime    # gate, section 6.4
```

### 6.3 Ordered Bazel commands (each through `python3 tools/bazel/run.py --timeout <s>`)

1. `mod graph` (900 s) and `build --nobuild //... --lockfile_mode=error`
   (900 s): baseline graph/lock check before any change, then again at the end.
2. `query 'tests(//...)'` and `query 'kind(py_test, //tests:all)'`: the
   denominators T and P, saved verbatim.
3. Site bring-up (section 9): `build //site:sveltekit_types`, then
   `test //site:svelte_check_test`, then `build //site:build` (1800 s each).
4. **The full run** (one invocation, 7200 s bound):
   `test //... --config=host-tools --jobs=4 --local_resources=cpu=4
   --test_env=FFMPEG=$FFMPEG --test_env=FFPROBE=$FFPROBE
   --test_output=errors --test_summary=detailed --keep_going
   --build_event_json_file=<lane artifacts>/full/bep.json`.
   Per-target status comes from the BEP file; per-module unittest counts from
   each `bazel-testlogs/.../test.log` (copied into lane artifacts). This
   run is executed once and recorded as-is. A rerun is allowed only if the
   first is killed by the timeout or the host gate (then both are recorded,
   the first as `ran_timeout`/`blocked_on_host`); it is never rerun to turn a
   failure into a pass.
5. Reproductions (section 7), one module at a time, plain unittest.

### 6.4 Host gate

Before each heavy step: if the 1-minute load average exceeds 24, wait (in the
background, not a foreground sleep) and re-check; every check is logged with
time and value in `bazel_full-host-gate.json`. After 90 minutes of continuous
gating the step is recorded `blocked_on_host` with the load series and the
lane proceeds with the remaining non-heavy work.

## 7. Known host-specific failures: naming and evidence

`bazel/known_host_failures.json` (owned) and the receipt carry one entry per
failing case:

```
{"case": "test_x.ClassName.test_name", "target": "//tests:test_x",
 "class": "dot_path_component" | "macos_process_inspection" | "other",
 "bazel_outcome": "FAIL" | "ERROR", "first_error_line": "<verbatim>",
 "plain_unittest_repro": {"command": "...", "cwd": "<worktree>", "outcome": "FAIL" | "ERROR" | "PASS"},
 "control_repro": {"path_kind": "dot_free_copy", "outcome": ...} | null,
 "baseline_repro": {"commit": "a16d02d...", "outcome": ...} | null,
 "cause": "<one sentence, M or I marked>", "claim_class": "M" | "I"}
```

Rules: the register lists what the run produced, not what root predicted;
a predicted failure that does not occur is recorded as `not_reproduced`; a
failure under Bazel that **passes** under plain unittest is a Bazel-graph
defect owned by this lane (fixed or reported), not a host failure. The
register is documentation only: no BUILD, macro or shim reads it.

Control copy for the dot-path class: `git -C <worktree> archive HEAD` unpacked
into a transient directory whose absolute path has no dot-prefixed component
(the session scratchpad), the same module run with plain unittest there, the
copy deleted afterwards; only the outcome lines are kept in lane artifacts.
Baseline reproduction for the macOS process class uses the same method at
commit `a16d02d` (optional; `null` with reason if not run).

## 8. `.local` investigation (calibration evaluator)

Question: is the failure a product defect (the code's behaviour depends on
where the checkout lives), or a correct refusal of a user-supplied path?

Method (no numerics beyond the existing unit cases): run each failing case in
the worktree and in the dot-free control copy; capture the traceback; locate
the raising guard; read whether that guard is applied to (a) only the
user-supplied relative part of a path, or (b) an absolute/resolved path that
includes the repository root.

Verdict rule (frozen):

- `product_defect`: the guard rejects a component of the **checkout prefix**
  (the repository root's own location), i.e. the same request succeeds from a
  dot-free path and fails from a `.local` path with no difference in the
  user-supplied value. Delivered as a root request with a minimal diff against
  the owning `scripts/*.py` (apply the dot check to the path relative to the
  allowed root, not to the absolute path) plus the failing case as its test.
  `scripts/tool_api.py` is root-owned; a diff there is requested, not applied.
- `test_fixture_assumption`: the product is location-independent but the test
  builds a path that includes the checkout prefix where the product expects a
  relative one. Delivered as a root request against the test (the lane does not
  own other test modules).
- `intended_refusal`: the refusal is documented contract behaviour for a value
  the user supplied; no change requested; the case is a host-location
  limitation recorded in section 7.
- `undetermined`: evidence insufficient; recorded with what was read.

Doctrine note: the refusal of dot-prefixed user paths protects private trees;
any proposed fix must keep refusing dot-prefixed components **below** the
allowed root.

## 9. `//site` protocol

1. `MODULE.bazel`: `npm.npm_translate_lock(name = "npm_site", pnpm_lock =
   "//site:pnpm-lock.yaml", data = ["//site:package.json",
   "//site:pnpm-workspace.yaml"], verify_node_modules_ignored =
   "//:.bazelignore")` and `use_repo(npm, "npm_site")`. No npm version literal
   is added; `site/package.json` and `site/pnpm-lock.yaml` stay the only npm
   version sites for the site.
2. **`allowBuilds` precondition.** `site/pnpm-workspace.yaml` lacks it (not
   owned). Order: (a) an attribute of `npm_translate_lock` in `MODULE.bazel`
   that satisfies rules_js 3.5.1 without editing the site file, if rules_js
   source shows one; else (b) a root request for the one line `allowBuilds:
   {}` with verification in a scratch copy carrying it (bazel_graph precedent),
   and `//site` reported `built_in_scratch_copy` until root applies it.
3. **Vendored `file:` carriers** (`@xoxd/theme`, `@xoxd/public-chrome`).
   Ordered options, the first that works is taken and recorded with the error
   text of any earlier one:
   1. rules_js native handling of `file:` directory packages in the lock,
      if it works without un-ignoring `site/vendor`;
   2. `bazel_dep(name = "xoxd_theme", version = "0.1.1")` and
      `bazel_dep(name = "xoxd_public_chrome", version = "0.1.0")` with
      `local_path_override(path = "site/vendor/<dir>")` (the vendored,
      integrity-verified bytes; no archive download), linked with
      `npm_link_package(src = "@<module>//:pkg")` and the lock entries
      replaced through rules_js package replacement. Requires the compliance
      reading of `BAZEL_GRAPH_S3.md` section 5 (both manifests declare Skeleton
      5.0.1 and no Effect: measured at freeze) and a `registry_modules.json`
      decision change requested from root (file not owned) or recorded in the
      owned supplement. Risk recorded at freeze: their `aspect_rules_js 2.9.1`
      dependency must resolve against the root's 3.5.1 (compatibility level
      unknown);
   3. none works: `//site` declared but `blocked`, exact errors recorded,
      metric 9 reported 0 of 2. Valid completion; no workaround that edits
      `site/vendor/**` or the site lock.
4. Pins: Node 22.13.1 (site engines `>=22.13 <23`), pnpm 11.25.0, TypeScript
   from the site lock. A second TypeScript toolchain repo is added only if a
   `ts_project` needs it (none planned).

## 10. Hosted CI job proposal (root request, text only)

Delivered in `bazel_full-root-requests.json` as a unified diff against
`.github/workflows/ci.yml` (and mirrored as `bazel/ci-bazel-full.draft.yml`),
superseding `tools/bazel/ci-bazel-job.draft.yml`. Frozen content constraints:

- separate job `bazel` on `ubuntu-24.04` beside `offline`, `timeout-minutes`
  from the measured local full-run time with margin, `continue-on-error: true`
  until root has seen it green twice;
- Bazel from the runner's bazelisk with `.bazelversion`; FFmpeg from the
  existing Nix dev shell (`cachix/install-nix-action` pinned as in `offline`),
  passed as `--test_env=FFMPEG=$(command -v ffmpeg)`; no credentials, no
  media, no model downloads, no remote cache;
- target set: `//...` with `--test_tag_filters=-requires-host-tools` unless
  the full run shows host-tool modules pass with only rules_js node (then the
  filter is dropped); the subset is justified per excluded tag with counts;
- cache notes: optional `actions/cache` of the disk cache and repository
  cache keyed on `MODULE.bazel.lock`, `web/pnpm-lock.yaml`,
  `site/pnpm-lock.yaml`; the action SHA is left to root to pin (the lane does
  not resolve it); cold vs warm runtime stated as I;
- Linux behaviour is U until a hosted run: the dot-path class should not occur
  on a runner checkout path (I) and the macOS process class may not apply (I).

## 11. Module graph, lock and network

- Registries: exactly the two pinned lines; no third registry, no
  `--registry` on the command line.
- Allowed fetches: Bzlmod metadata/archives from the two pinned registries for
  modules already in the graph or added under section 9.3.2 (expected: none,
  since `local_path_override` reads the vendored bytes), and npm archives named
  with integrity in `site/pnpm-lock.yaml` (the same set `pnpm install
  --frozen-lockfile` fetches). This reading is the lane's and is flagged for
  root; if root rejects it, `//site` stays `declared_unbuilt`.
- `MODULE.bazel.lock` is regenerated only by Bazel and committed with the
  change that caused it; `git diff` of the lock is summarised in the receipt
  (added/removed module keys and extension entries).

## 12. Structural test extension (`tests/test_bazel_graph_s3.py`)

Added assertions (stdlib only, no Bazel/network):

- `site/BUILD.bazel` exists, is an owned package in the stray-file check,
  declares `svelte_check_test` and `build`, loads `@npm_site//:defs.bzl`, and
  contains no private-tree needle;
- `MODULE.bazel` has exactly two `npm_translate_lock` calls (`web`, `site`),
  each pointing at its own `pnpm-lock.yaml`, no `npm_import`;
- `site/package.json` vs `site/pnpm-lock.yaml` importer: Skeleton 5.0.1 for
  both packages, Effect absent or exactly 4.0.1, TypeScript 6.0.3;
- classification lists in `tests/BUILD.bazel` equal the union of
  `tools/bazel/test_classification.json` and
  `bazel/test_classification_s3_full.json`; every module named exists;
- `bazel/known_host_failures.json` schema (section 7), every `case` names an
  existing module/class/method, and no BUILD or `.bzl` file references it;
- no `manual` tag and no case-level skip mechanism added to the shim or
  macros since the baseline;
- if `local_path_override` is used, its path is under `site/vendor/` and the
  module name/version equal the vendored `MODULE.bazel`.

Negative self-checks (temp copies): a third `npm_translate_lock` with an
Effect 3 lock, a known-failure entry naming a missing case, a `manual` tag on a
unittest target, and a private-tree needle in `site/BUILD.bazel` must each fail.

## 13. Explicit unknown fields the receipts must carry

Each is a key in `bazel_full-handoff.json` with a value or `"unknown"` plus
reason; none may be omitted:

- `full_run_status` (`ran_complete` | `ran_timeout` | `blocked_on_host`),
  `full_run_exit`, `full_run_wall_s`, `full_run_command`;
- `test_targets_total` (T), `python_modules_total` (P), and counts
  `passed`, `failed`, `timeout`, `flaky`, `no_status`, `not_run`;
- `ffmpeg_modules_run_with_ffmpeg` (k of F) and
  `ffmpeg_modules_all_cases_skipped`;
- `known_host_failures` (count, cases) and `unexplained_failures` (count, cases);
- `dot_local_verdict`, `dot_local_raising_line`, `dot_local_fix_requested` (bool);
- `macos_process_cases_baseline_repro` (`reproduced` | `not_reproduced` | `not_run`);
- `site_check_under_bazel`, `site_build_under_bazel`
  (`passed` | `built_in_scratch_copy` | `blocked` | `declared_unbuilt`),
  `site_vendor_carrier_method` (9.3 option or `none`),
  `site_allow_builds_method`;
- `site_build_parity_with_pnpm` (`equal` | `differs` | `not_compared`);
- `mod_graph_exit`, `lockfile_mode_error_exit`, `new_bazel_deps`,
  `new_extension_repos`, `npm_archives_fetched_for_site` (count, bytes);
- `linux_behaviour` (`unknown` until a hosted run), `ci_bazel_job`
  (`requested_not_applied`), `ci_expected_runtime_min` (I);
- `host_load_gate_waits` (count, longest);
- `remote_cache` (`not_configured`), `listening_claims` (`none`),
  `signal_path_changed` (`false`), `bazel_replaces_just` (`false`).

## 14. Receipts

`bazel_full-contract-freeze.json` (Phase 2: baseline facts re-measured),
`bazel_full-host-gate.json`, `bazel_full-full-run.json` (per-target table,
per-module counts, BEP summary), `bazel_full-known-host-failures.json` (mirror
of the register with reproductions), `bazel_full-site.json`,
`bazel_full-tests.json` (section 6.1 commands and counts),
`bazel_full-root-requests.json` (`.github/workflows/ci.yml` diff; any
`site/pnpm-workspace.yaml`, `tools/bazel/*`, `registry_modules.json`,
`scripts/*` fix diffs; `public_site-handoff.json` `bazel_graph: absent` field
now stale once `site/BUILD.bazel` exists), `bazel_full-handoff.json`
(section 13 keys, commit shas, R-N13 citation).

## 15. Experiment and preregistration

This lane runs **no experiment**: no arms, seeds, held-out data, scoring or
tuning. The full run is an execution record, not a comparison, so no
preregistration applies. The one sealed expectation, written here before any
run, is root's relayed prediction in section 3 (5 calibration cases, 2 macOS
process cases); Phase 2 reports observed against it without adjusting the
graph to match.

## 16. Phase 2 amendments (recorded deviations, with cause)

Recorded during implementation; the frozen sections above are unchanged. Every
value named here is in the receipts (section 14).

1. **Site gate (deviation from 4.1, cause: 9.2 and 9.3).** rules_js 3.5.1
   fails `npm_translate_lock` when the lock's `pnpm-workspace.yaml` has no
   `allowBuilds` (`npm_translate_lock_helpers.bzl` `_verify_lifecycle_hooks_specified`,
   called unconditionally by `parse_and_verify_lock`; no attribute bypasses it,
   and the only other source is `pnpm.onlyBuiltDependencies` in
   `site/package.json`, also not owned), and one refused translation fails the
   whole `npm` extension, `//web` included. The `npm_site` translation therefore
   sits in a `dev_dependency = True` usage, and `.bazelrc` carries
   `common --ignore_dev_dependency` and `common --deleted_packages=site`, so the
   committed tree loads exactly the bazel_graph packages plus `//bazel`.
   `tests/test_bazel_graph_s3.py` requires the gate to be present exactly while
   a prerequisite is missing. `MODULE.bazel.lock` is byte-identical with and
   without the gate (measured).
2. **Carrier method (9.3).** Option 1 without un-ignoring fails
   (`no such package 'site/vendor/xoxd-public-chrome': Package is considered
   deleted due to --deleted_packages`). Option 2 cannot redirect: rules_js
   generates the first-party store with a fixed main-repository label
   `//site/vendor/<dir>:pkg` and skips `replace_packages` for
   `resolution.type == "directory"` (`npm_translate_lock_helpers.bzl` line 508);
   a scratch probe with both `local_path_override`s resolved the module graph
   and failed with the same deleted-package error. Option 1 works once the
   root-owned `.bazelignore` replaces `site/vendor` with
   `site/vendor/xoxd-theme/test` (the carrier's own test package, whose
   `//:test_inputs` labels only resolve inside its own module); the vendored
   files are not edited. `//site` is therefore `built_in_scratch_copy` until
   root applies both lines (scratch = lane HEAD + the three requested root
   changes).
3. **Owned site build runner.** The site's agents page reads
   `<site>/../program/tools.json` at prerender time; the shared runner builds in
   a scratch directory without that sibling. `bazel/site_build.mjs` (owned)
   lays out `<scratch>/site` and `<scratch>/program/tools.json`; sync and check
   reuse `//tools/bazel:web/sveltekit.mjs` unchanged. The root package exports
   `program/tools.json` and `//site:tool_registry` copies it into the package
   (rules_js copies only same-package files to the output tree).
4. **`//bazel` package.** `bazel/BUILD.bazel` exports the site runner and an
   `all_files` group added to the unittest data. No BUILD or `.bzl` file reads
   `bazel/known_host_failures.json`.
5. **Host gate.** `bazel/host_gate.py` logs each reading to the lane artifacts;
   the receipts carry the series. The site bring-up wait was superseded so that
   the first opening went to the full run.
