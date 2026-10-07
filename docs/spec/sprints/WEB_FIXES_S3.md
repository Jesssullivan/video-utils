# S3 web_fixes lane contract: source fixes for the defects and axe violations found by web_tests

Status: **Phase 1 contract freeze**, 2026-10-07. Lane `web_fixes`, sprint
`20261007-s3`, branch `sprint/20261007-s3/web_fixes`, worktree
`.local/sprint3/web_fixes`. Tracker: Linear TIN-5724.
Baseline: `a077766da88b1cccf8190f4b34fda0893723b9c4` (main after the web_tests
admin merge).
Authority: `docs/spec/sprints/20261007-S3.md`, `docs/spec/sprints/WEB_TESTS_S3.md`
(test protocol this lane must not weaken), repository `AGENTS.md`,
R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13.
Root administers review, signed merge, `just` recipes, CI, publication and
Linear. This lane never pushes, merges, writes Linear, edits root-owned or
other lanes' files, downloads models or browsers, or starts a daemon.

No install, check, build, unit, browser, axe or Python test run was executed
in this phase. The only commands run were read-only inspection of the
worktree (`cat`, `grep`, `git status/log/rev-parse/check-ignore`). Every
number in sections 3 and 4 marked "baseline" is quoted from the committed
web_tests receipts, not re-measured here.

## 1. Scope

In scope (fix in source; tests change only to stop tolerating the defects):

1. **F1 `capture_interval_number_binding`.** `IntervalPicker.svelte` lines
   18-19 and `routes/sources/[id=artifactid]/capture/+page.svelte` line 23 call
   `.trim()` on state bound to `<input type="number">`; Svelte assigns a number
   (or null), so typing throws `trim is not a function` and the live setup
   warning never renders. Fix: the interval state is always a string in both
   components. Typing any value (inside or outside the first five seconds,
   empty, cleared, partial such as `-` or `1.`) throws nothing; the
   `data-setup-warning` panel appears as soon as the typed start overlaps the
   first five seconds and `reviewed_candidate` is disabled at the same moment.
2. **F1b same-class audit.** There are 7 `type="number"` inputs in 5 files
   under `web/src` (`IntervalPicker` x2, `SpanAudition` x2, `AnnotationPanel`
   x1, `KnobField` x1, `ProcessForm` x1). `SpanAudition.svelte` line 20 and
   `AnnotationPanel.svelte` line 56 have the same number-bound `.trim()`
   shape. Each of the 7 is typed into in a browser test; any that throws is
   fixed the same way. Sites that do not throw are left untouched and recorded
   as such.
3. **F2 `capture_action_drops_run_selection`.** The measure, save and author
   form actions post to `?/measure`, `?/save`, `?/author`, which replaces
   `?run=`. Fix: the chosen baseline run stays selected after any of the three
   actions (success or typed refusal), so Measure and Save stay enabled and the
   typed interval is kept. The run is still selected only from the eligible
   baseline list by the same `isRunId` + `eligible.find` rule; a run id that is
   absent or ineligible still selects nothing.
4. **F3 `favicon_missing`.** One original hand-written SVG at
   `web/static/favicon.svg` (no third-party asset, no embedded raster, no
   script, no external reference) linked from `web/src/app.html`. No `/favicon.ico`
   request that answers 404 on any scanned route.
5. **F4 axe violations.** All 42 baseline entries (62 nodes) of
   `web/e2e/a11y-baseline.json`:
   - `color-contrast`: 30 entries / 46 nodes, 15 scans x 2 schemes. Selectors
     include `.preset-filled-primary-500` (13 uses in source),
     `.preset-filled-error-500`, primary-nav links, tonal buttons on the
     source, process, compare, review and upload pages. Fixed to WCAG 2 AA
     (4.5:1 normal text, 3:1 large text) with Skeleton cerberus theme tokens or
     the existing `--vu-*` tokens. No new hex/rgb literal is introduced where a
     token exists; any new literal is listed in the receipt with its reason.
   - `label`: 4 entries / 4 nodes (critical), `input[type="file"]` on
     `/upload` and its refused state. Fixed with a programmatic `<label>`
     (visible text). The other `/upload` controls keep their existing labels.
   - `heading-order`: 4 entries / 4 nodes (moderate), `h3` after `h1` on
     `/runs/[id]/compare` (`ABCompare`) and `/runs/[id]/review` (`FlagsList`;
     `TimingTable` and `AnnotationPanel` are checked too). Fixed by heading
     level, keeping the visual size class.
   - `link-in-text-block`: 4 entries / 8 nodes (serious), `.anchor` links to
     `/upload` and `/runs` inside paragraphs on `/`. Fixed with a non-colour
     cue (underline) on in-text anchors, applied through one shared rule.
6. **Tests.** The two `test.fail` tests in `web/e2e/capture.spec.ts` become
   ordinary tests. The 4 `expectConsoleError(NUMBER_BINDING_DEFECT, ...)`
   tolerances and the default `/favicon.ico` tolerance in
   `web/tests/e2e-support.ts` are deleted, so those errors become unexpected
   again. `web/e2e/a11y-baseline.json` shrinks to
   `{"schema_version": 1, "violations": []}`; a residual entry is allowed only
   with a written reason in the receipt (target zero).
7. **Receipts** under `docs/agent-notes/sprints/20261007-s3/web_fixes-*.json`.

Out of scope, not claimed:

- Route behaviour, API contracts, BFF request bodies, job semantics, the
  setup-interval rule (owned by the control API), admission, polling.
- A light theme. `app.html` fixes `class="dark"` and `color-scheme: dark`, so
  the "light" scans measure the same dark page under
  `prefers-color-scheme: light`. Whether the two schemes render differently is
  recorded (`scheme_changes_rendering`), not assumed.
- `refusal_text_prototype_key` (2 `it.fails` unit tests) and
  `unmapped_refusal_codes`: not in this lane's definition of done; carried and
  counted in the unit receipt.
- The axe protocol (tags, 19 scans x 2 schemes, no disabled rule, no
  exclusion), `playwright.config.ts`, `package.json`, the lockfile, pins
  (Skeleton 5.0.1, Effect 4.0.1 stay), fixtures and their idempotency keys,
  scanner configuration.
- Manual accessibility audit, screen-reader or other assistive-technology
  testing, WCAG conformance, Firefox/WebKit, visual regression, any DSP,
  detector, profile, master, listening, ~32 Hz or note-correctness claim.

## 2. Owned files

| Path | Role |
| --- | --- |
| `docs/spec/sprints/WEB_FIXES_S3.md` | This contract |
| `web/src/**` | Source fixes F1-F4 (components, routes, `app.css`, `app.html`); unit tests next to any new pure helper |
| `web/static/favicon.svg` | New original icon (directory is new; `web/BUILD.bazel` already globs `static/**`) |
| `web/e2e/*.spec.ts`, `web/e2e/a11y-baseline.json` | Un-fail the two tests, drop tolerances, add the F1b and favicon checks, empty the baseline |
| `web/tests/**` | Remove the default favicon tolerance |
| `tests/test_web_stack.py` | Only if a static assertion there names changed markup; no assertion is weakened |
| `docs/agent-notes/sprints/20261007-s3/web_fixes-*.json` | Receipts |

Not owned, never edited: `web/playwright.config.ts`, `web/package.json`,
`web/pnpm-lock.yaml`, `web/svelte.config.js`, `web/serve.js`,
`web/Containerfile`, `web/BUILD.bazel`, `web/e2e/fixtures/**` generator
outputs, `tests/test_web_house_stack_s3.py` and every root-owned file.
Needed changes there go to `web_fixes-root-requests.json` as exact diff text.
Known request at freeze: `web/Containerfile` copies `src/` only, so the image
build would omit `static/` (`COPY static/ ./static/` before the build step).

Run outputs: the unedited Playwright config and helper write to the
gitignored `artifacts/s2/web_tests/` inside this worktree. After each run the
lane copies `report.json`, `metrics.jsonl` and the a11y `summary.json` to
`artifacts/s2/web_fixes/<e2e|a11y|unit|check|build|python>/` and receipts
cite those copies with sha256.

## 3. Completion metrics

Claim classes: **contract** (static statement about committed files),
**behaviour** (a test observed it in Chromium against the mock or in Node),
**measurement** (a counted tool result). None is a listening, manual or
assistive-technology claim. Every metric is reported as value/denominator; a
metric that cannot be evaluated is `null` with a reason, never a pass.

| ID | Metric | Target | Class |
| --- | --- | --- | --- |
| X1 | `pnpm run check`: svelte-check errors (warnings reported separately) | 0 errors | measurement |
| X2 | `pnpm run build` exit code; `build/client/favicon.svg` present | 0; present | measurement |
| X3 | `test:unit`: files passed / files; tests passed, failed, expected failures | 0 failed; expected failures 2/2 carried (`refusal_text_prototype_key`) or fewer; baseline 153 passed + 2 expected of 155 in 13 files | behaviour |
| X4 | `test:e2e`: expected / total, with `test.fail` count and unexpected count | 0 expected failures, 0 unexpected, 0 flaky, 0 skipped; baseline 50 passed + 2 expected failures of 52 in 11 files | behaviour |
| X5 | F1: typed-interval cases without page error / cases; warning shown when start < 5 s / such cases; warning absent otherwise / such cases | all/all for each | behaviour |
| X6 | F1b: number inputs typed without page error / 7; sites changed / sites that threw | 7/7; equal | behaviour |
| X7 | F2: actions after which `select[name="run"]` still holds the run and Save is enabled / actions exercised (measure ok, save refused 422, save ok) | 3/3; `author` recorded separately or `null` with reason | behaviour |
| X8 | F2 negative: forged or ineligible `run` values that select nothing / values tried | all/all | behaviour |
| X9 | F3: scenarios with a `/favicon.ico` 404 or any favicon console error / e2e scenarios; `GET /favicon.svg` status and content type | 0/N; 200 `image/svg+xml` | behaviour |
| X10 | Declared console-error tolerances remaining for the three defects / 5 at baseline (4 number-binding + 1 favicon default) | 0/5 | contract |
| X11 | `test:a11y`: scans executed / 38; violations total; violations outside baseline; per scheme (light 19, dark 19) | 38/38; 0; 0 | measurement |
| X12 | Baseline entries remaining / 42, by rule (30, 4, 4, 4); nodes remaining / 62 | 0/42; 0/62; each residual has a reason | measurement |
| X13 | axe `incomplete` results and nodes (baseline 34 / 130) | reported, not a target; an increase is listed by rule and route | measurement |
| X14 | New colour literals added under `web/src` / colour declarations changed | 0, or each listed with reason | contract |
| X15 | Doctrine markers unchanged: user vs detector shapes (`solid`/`dotted`), no-autoplay (15 media elements paused, 0 `play()` calls), no first-5-s auto-confirm (0 non-GET on load, acknowledgement never added by the page), 0 high-pass/low-cut/notch controls | existing e2e tests pass unmodified | behaviour |
| X16 | Python modules: tests run, passed, failed, skipped (with skip reasons) per module | 0 failed | behaviour |
| X17 | Files changed outside section 2 | 0 | contract |

Pins are not a metric of this lane but are re-read: Skeleton 5.0.1 and Effect
4.0.1 unchanged (`git diff` of `package.json` and the lockfile is empty).

## 4. Test protocol

Environment: Node 22, `pnpm install --frozen-lockfile --offline` in
`web/` (store already populated; no network install), Chromium from the
existing Playwright cache through `web/tests/browser-ladder.ts` (no download;
a missing browser is a typed skip and the metric is `null`, not met). One
worker, zero retries, loopback only, mocked control API replaying the 41
committed synthetic fixtures in `web/e2e/fixtures/control-api/`. Fixture ids
come from `ids.json`; no real take, no real control API. Every command has an
explicit timeout (check 300 s, build 300 s, unit 300 s, e2e 600 s, a11y 600 s,
each Python module 900 s); at most one of them runs at a time.

Order, from `web/` unless stated:

1. `pnpm run check`
2. `pnpm run build`
3. `pnpm run test:unit` (vitest, `src/**/*.test.ts`, fast-check seed 20261007, 200 runs)
4. `pnpm run test:e2e` (`--project=e2e`, 11 spec files)
5. `pnpm run test:a11y` (`--project=a11y`, `a11y-routes.spec.ts`: 16 routes + 3
   states, light and dark, tags `wcag2a wcag2aa wcag21a wcag21aa wcag22aa
   best-practice`, nothing disabled or excluded)
6. From the worktree root, one module at a time:
   `PYTHONPATH=tests python3 -m unittest test_web_stack -v` (owned) and
   `PYTHONPATH=tests python3 -m unittest test_web_house_stack_s3 -v`
   (directly affected: it reads the baseline file, the axe spec and the
   helper). `test_web_runs_s3` and `test_web_processing_s3` are run only if a
   file they read statically under `web/src` is changed; the receipt states
   which were run and why. The full suite is root's.

Tests added or changed (all in owned files):

- `capture.spec.ts`: the two former `test.fail` tests as plain tests; a
  parametrised typing test (X5) over start values `0`, `1`, `4.999`, `5`,
  `5.5`, `-`, `1.`, empty-after-typing, and end-only typing; F2 after measure,
  after a refused save and after an accepted save; X8 with a syntactically
  valid but unlisted run id and a malformed one.
- `process.spec.ts` / `runs.spec.ts`: type into the remaining number inputs (X6).
- `library.spec.ts` or `headers.spec.ts`: `GET /favicon.svg` and the icon link (X9).
- A vitest file next to any new pure helper (for example a string coercion in
  `processing/setup.ts`) with unit cases for number, null, undefined and string inputs.
- No existing assertion is deleted except the tolerances in section 1 item 6.

A fix is accepted only when the previously failing assertion passes and the
tolerance for it is gone; un-failing a test without the source change is not
completion. If a fix cannot be made within scope, the test stays `test.fail`,
the baseline entry stays, and the receipt says so (valid completion, reported
as not met).

## 5. Receipts and required unknown fields

Files: `web_fixes-contract-freeze.json`, `-check-build.json`, `-unit.json`,
`-e2e.json`, `-a11y.json`, `-python.json`, `-root-requests.json`,
`-handoff.json`. Each carries `schema_version`, `lane`, `sprint`, `tracker`,
`ruling`, `basis` (lane commit, baseline commit), `command`, `exit_code`,
`claim_class`, numerators and denominators, and this block with explicit
`null` + `_reason` where not established:

- `manual_accessibility_audit: null`, `screen_reader_acceptance: null`,
  `wcag_conformance: null` (axe automated rules only; say so in the a11y
  receipt and the handoff in plain words)
- `axe_version`, `axe_rules_evaluated_count`, `axe_incomplete_count`,
  `axe_incomplete_nodes`
- `scheme_changes_rendering` (true/false/null) and
  `light_theme_exists: false`
- `contrast_ratios_source` ("axe node data", per fixed selector before/after,
  or `null` where axe gives none)
- `browser_used`, `browser_version`, `browser_source`,
  `firefox_webkit_behaviour: null`
- `real_control_api_under_playwright: null`, `real_take_facts_in_fixtures: false`
- `fixture_drift` (the committed fixtures may be behind the registries on main)
- `containerfile_serves_static: null` (root-owned; not built by this lane)
- `author_action_keeps_run` (true/false/null)
- `unit_expected_failures_carried` (count and code)
- `listening_claims: null`, `low_register_claims: null`,
  `note_correctness_claims: null` (none made)
- `residual_baseline_entries` (list, each with `reason`), `new_colour_literals` (list)
- `flaky_retries: 0` expected; any rerun is recorded with its cause

## 6. Experiment and preregistration

This lane runs no experiment: no arms, seeds, held-out data or scoring beyond
the pass/fail and count metrics above, and no detector, profile or master is
touched or adopted. What is sealed before any run is the measurement
protocol: the axe tags, scans and schemes of `WEB_TESTS_S3.md` section 9 stay
byte-for-byte as committed, the baseline may only shrink, and the baseline
file is rewritten from a completed 38/38 run, never edited to match a
partial one.

## 7. Hand-offs to root

Text only, in `web_fixes-root-requests.json`: the `web/Containerfile`
`static/` copy; any root-owned test that pins markup changed here; fixture
regeneration if main's registries moved. Root reviews, signs and merges.

## 8. Phase 2 outcome (2026-10-07)

Sections 1-7 are the frozen contract and are unchanged. What the implementation
did, with the figures in `docs/agent-notes/sprints/20261007-s3/web_fixes-*.json`:

- F1: the two interval inputs are read through their `value` text (`value=` +
  `oninput`), so the state never changes type. No helper was added, so no new
  unit test file exists.
- F1b: the contract named two more `.trim()` sites; the browser tests found a
  third (`ProcessForm.svelte`, on submit). Three components threw when run
  unfixed (`SpanAudition`, `AnnotationPanel`, `ProcessForm`) and all three were
  fixed the same way. `KnobField` did not throw and is untouched.
- F2: the three action URLs carry `&run=<chosen run>`; the load rule is unchanged.
- F3: `web/static/favicon.svg`, linked from `app.html`.
- F4: `preset-filled-primary-500` -> `preset-filled-primary-300-700` and
  `preset-filled-error-500` -> `preset-filled-error-200-800` (Skeleton paired
  presets, theme tokens only); anchors underlined through the cerberus
  `--typo-anchor--*` tokens; a visible `<label>` on the upload file input;
  `h3` -> `h2` in `ABCompare`, `FlagsList` and `TimingTable`.
- The baseline is empty. The axe result is an automated check only: not a manual
  audit, not a screen-reader test, not a WCAG conformance claim.
