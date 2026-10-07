# quarto_fix lane: report devShell quarto/pandoc fix and one render attempt (S2R)

Sprint `20261007-s2r`, Linear TIN-5491 (lane work only; root writes Linear).
Branch `sprint/20261007-s2r/quarto_fix`, worktree
`.local/sprint2/quarto_fix`, base commit `7d0e11e`. Contract frozen
2026-10-07T01:42Z, before any fix or render work.

Authority: operator ruling recorded in
`docs/agent-notes/2026-10-07-s2-operator-rulings.md` (row "Quarto report
(D6)"): approve the flake.nix quarto/pandoc fix plus **one** more bounded
render attempt; if it fails again, the plain HTML report from
`scripts/report.py` is final for D6. R-HOOK-CONVERGENCE-20261004
(TIN-3692 comment 98cf680c-7299-4949-bfb2-60079053ad43) R-N13 for receipts;
repository `AGENTS.md`.

## 1. Measured starting state (read in this phase, no new numerics)

Facts from `docs/agent-notes/sprints/20261006-s2/report_d6-render-attempt.json`
and read-only inspection of the local Nix store:

| Fact | Value | Class |
| --- | --- | --- |
| Locked nixpkgs rev (`flake.lock`) | `2c423e03bbafcff28bfadc6781a4a8257f205cb5` | measured |
| `pkgs.quarto` at that rev | `quarto-1.10.18` (`/nix/store/skzd95zv...-quarto-1.10.18`) | measured |
| Wrapper default | `QUARTO_PANDOC=${QUARTO_PANDOC-'/nix/store/vqa60811...-pandoc-cli-3.7.0.2/bin/pandoc'}` (shell default expansion, so an exported `QUARTO_PANDOC` wins) | measured (read `bin/quarto`) |
| Prior attempt | 1 of 1 used, exit 1, 1172.14 s, 21/21 knitr chunks ran, no HTML | measured (prior receipt) |
| Blocking line | `Aeson exception: Error in $: Unknown option "syntax-highlighting"` | measured (prior receipt) |
| `quarto.js` 1.10.18 | declares `kSyntaxHighlighting`; `highlight-style` is marked "Deprecated: use `syntax-highlighting` instead" | measured (grep) |
| `quarto-1.9.37` in store | also contains `kSyntaxHighlighting` (18 hits) and its wrapper also defaults to pandoc-cli-3.7.0.2 | measured (grep) |
| nixpkgs `quarto/package.nix` (1.10.18 sources in store) | `src` is the upstream release tarball (`quarto-1.10.18-macos.tar.gz`, hash `sha256-3danGp4E...`); install **removes** the vendored `bin/tools/$arch/pandoc` and links nixpkgs `pandoc` (3.7.x) | measured (read source) |
| nixpkgs haskell set | `pandoc` 3.7.x default; `pandoc-cli_3_9_0_2` exists with `hydraPlatforms = lib.platforms.none` (not cached; would need a Haskell source build, and its `pandoc` library input resolves to 3.7) | measured (read source) |
| `reports/_quarto.yml` | does not set `syntax-highlighting` or `highlight-style` | measured |

Inference (I1): the cause is the quarto/pandoc pairing in the nixpkgs wrapper,
not the report source. Quarto 1.10.18 writes the pandoc option
`syntax-highlighting`, which pandoc 3.7.0.2 does not know. Removing an option
from `reports/_quarto.yml` cannot fix it because the option is not set there.

## 2. Chosen fix (minimal, evidence-based)

Use the pandoc binary that upstream Quarto 1.10.18 ships for itself, taken from
the **same hash-pinned release tarball nixpkgs already uses** (`pkgs.quarto.src`),
and point the `report` devShell at it with `QUARTO_PANDOC`. No new flake input,
no `flake.lock` change, no nixpkgs bump, no Haskell compilation, no new URL or
hash. Only the `report` attribute changes.

Planned `flake.nix` diff (Phase 2 implements exactly this, modulo path layout
handling):

```nix
# inside the per-system let block
quartoBundledPandoc = pkgs.runCommand "quarto-${pkgs.quarto.version}-bundled-pandoc" {
  src = pkgs.quarto.src;   # the tarball nixpkgs already pins by hash
} ''
  mkdir unpack "$out" "$out/bin"
  tar -xzf "$src" -C unpack
  t=$(find unpack -path "*/bin/tools/${pkgs.stdenv.hostPlatform.parsed.cpu.name}/pandoc" | head -n 1)
  [ -d "$t" ] && t="$t/pandoc"
  install -m 0755 "$t" "$out/bin/pandoc"
'';
# ...
report = pkgs.mkShell {
  packages = core ++ [ pkgs.R pkgs.quarto ];
  # nixpkgs pairs quarto 1.10.18 with pandoc 3.7.0.2, which rejects
  # `syntax-highlighting`; use the pandoc upstream ships with this quarto.
  QUARTO_PANDOC = "${quartoBundledPandoc}/bin/pandoc";
};
```

Rejected alternatives and the reasons:

- (A) `QUARTO_PANDOC = ${pkgs.pandoc}`: the locked `pkgs.pandoc` is 3.7.x. It
  is the same failing version.
- `haskellPackages.pandoc-cli_3_9_0_2`: not built by Hydra. It needs a heavy
  Haskell source build and a pandoc 3.9 library override.
- (B) Bump the global nixpkgs input: this changes the default shell and CI. No
  locked-later rev is known to pair quarto with pandoc 3.8 or newer, because
  nixpkgs haskell still says "We are still using pandoc == 3.7.*".
- (C) Pin an older quarto (1.9.37 also uses `syntax-highlighting`) or add a
  second nixpkgs input. This is a larger closure and a new lock entry, and the
  compatibility is unproven.
- Edit `reports/_quarto.yml`: it is not the cause.

**Fallback (used only if the preflight in section 4 fails, at most once, and
before the render attempt):** pin the upstream `jgm/pandoc` release binary for
the version that the bundled binary reports or Quarto 1.10.18 documents. Pin
it by `fetchurl` with a sha256 in the same `report` let-binding only. Record the
URL and hash. If the fallback preflight also fails, the outcome is
`render_blocked_final` with zero render attempts used, and the plain HTML
report is final.

## 3. Scope and owned files

Owned (writes allowed only here):

- `flake.nix`: only the `report` devShell and a new let-binding it uses.
  `default`, `analysis`, `ml` and `formatter` stay byte-identical in effect,
  meaning their drvPaths are unchanged.
- `flake.lock`: expected **unchanged**. Any change is a recorded deviation
  with a reason.
- `reports/`: no edit planned. A change is allowed only if the render shows a
  report-source defect after the fix. That would be recorded, and it does not
  earn a second render.
- `docs/spec/sprints/QUARTO_FIX_S2R.md` (this file).
- `docs/agent-notes/sprints/20261007-s2r/quarto_fix-*.json`, which holds the
  receipts `quarto_fix-render-attempt.json` and `quarto_fix-handoff.json`.

Generated outputs go only under
`.local/sprint2/quarto_fix/artifacts/s2/quarto_fix/`, which is gitignored:
`bundles/`, `preflight/`, `render/attempt-1.log`, `render/demo.html`, and
moved in-tree products. Rendered HTML, PNG and log products are never
committed.

Out of scope and untouched: root-owned files (`scripts/tool_api.py`,
`program/tools.json`, `just/workflow.just`, `scripts/review_server.py`,
`scripts/mcp_server.py`, `program/models.json`, `program/linear.json`,
`docs/spec/PROJECT.md`). Also untouched: `scripts/report.py`,
`scripts/report_bundle.py`, `tests/`, other worktrees, `artifacts/runs/*`
(read-only), `/Users/jess/Documents`, `/Users/jess/Desktop`, Linear, model
downloads, daemons, host or plugin config, push, merge and main. A
just-recipe wish goes to root through `root_owned_changes_requested`.

## 4. Protocol (Phase 2/3, frozen here)

All heavy steps run one at a time with explicit timeouts. Nix runs through the
local-build-guard wrapper. If that wrapper picks the existing approved remote
builder, the receipt records it.

1. **Default-shell invariance (eval only).** Before and after the edit, run
   `nix eval --raw .#devShells.aarch64-darwin.{default,analysis}.drvPath`
   (timeout 600 each). The before-values come from base `7d0e11e` via
   `git+file://<worktree>?rev=7d0e11e`. They must be equal. Also run
   `nix eval --raw .#devShells.{aarch64-darwin,x86_64-linux}.report.drvPath`.
   This is evaluation only and builds nothing for Linux. Record `sha256` of
   `flake.lock` before and after.
2. **Bundle.** Run `timeout 600 python3 scripts/report_bundle.py build --run-dir
   /Users/jess/git/video-utils/artifacts/runs/20261006T041633Z-990aa1bd6737
   --output-dir <worktree>/artifacts/s2/quarto_fix/bundles`. The analysis run
   is auto-resolved, as in the prior D6 bundle. Only if auto-resolution
   refuses, add `--analysis-run-dir
   /Users/jess/git/video-utils/artifacts/runs/20261006T034521Z-a0def0c43eac`
   and record why. Then `verify --bundle-dir <B> --check-origin` must return
   `verified`. This step uses metadata only, decodes no media and invokes no
   FFmpeg. Record the bundle sha256 and whether it equals the prior
   `d3cfb5c7...`. Equality is a reproducibility observation, not a gate.
3. **Preflight (not a render).** Run `timeout 1800 nix develop .#report
   --command sh -c 'printf "%s\n" "$QUARTO_PANDOC"; "$QUARTO_PANDOC"
   --version | head -n 1; printf "x\n" | "$QUARTO_PANDOC" -f markdown -t html
   --syntax-highlighting=pygments >/dev/null && echo SH_OK'`. Pass means
   `QUARTO_PANDOC` resolves to the bundled-pandoc store path, the version is
   at least 3.8, and `SH_OK` is printed. Record seconds, exit code, the
   version line and the store path. On failure, use the section 2 fallback
   once, then repeat this preflight once.
4. **Exactly one render attempt.** This runs from the worktree root with an
   absolute `B`. The command is the prior D6 command plus pandoc probes. Only
   the pandoc pairing changes:

   ```
   /usr/bin/time -p timeout 1800 nix develop .#report --command sh -c \
     'quarto --version; R --version | head -n 1; printf "QUARTO_PANDOC=%s\n" "$QUARTO_PANDOC"; "$QUARTO_PANDOC" --version | head -n 1; quarto render reports/demo.qmd -P run_dir="$1"' \
     sh "$B" > artifacts/s2/quarto_fix/render/attempt-1.log 2>&1
   ```

   `run_dir` is the documented parameter name in `reports/demo.qmd`; its value
   is the bundle dir. There are no retries, whatever the outcome.
5. **Products.** Move `reports/_render/demo.html` (the `_quarto.yml`
   output-dir) or `reports/demo.html`, whichever exists, into
   `artifacts/s2/quarto_fix/render/`. Remove the in-tree `reports/.quarto/`,
   `reports/_render/` and `reports/*_files/`, recording what was moved or
   removed. Measure the HTML sha256 and bytes. Count `http(s)://` references
   and `<script src=` remote references, and check for MathJax. That check
   settles the prior open question of whether `html-math-method: plain` from
   `_quarto.yml` merged. Count `verified` against `refused:` status strings in
   the HTML. Never run `git add` on a product.
6. **Tests.** From the worktree root, with `FFMPEG` and `FFPROBE` exported to
   `/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/{ffmpeg,ffprobe}`,
   run `PYTHONPATH=tests python3 -m unittest test_report_bundle test_report -v`.
   The fixtures are the existing synthetic fixtures in those modules. No new
   test module is in scope, since `tests/` is not owned. Record
   discovered/passed/failed/errors/skipped. The prior baseline was 42/42.
   Root runs the full suite, `just check` and `just test-rust`. The lane
   shows these are unaffected through the step 1 drvPath equality, because
   the CI command is `nix develop --no-write-lock-file --command just ...`,
   which uses the default shell.

## 5. Completion metrics (denominators and claim classes)

| Metric | Target or record | Denominator | Class |
| --- | --- | --- | --- |
| render_attempts_used | at most 1 | 1 approved | measured |
| default_shell_drvpath_unchanged | true | 2 shells (default, analysis) on aarch64-darwin | measured |
| flake_lock_unchanged | true (else deviation reason) | 1 file | measured |
| report_shell_eval_ok | recorded | 2 systems (aarch64-darwin, x86_64-linux; eval only) | measured |
| preflight_syntax_highlighting_accepted | recorded | 1 preflight (+ at most 1 after fallback) | measured |
| pandoc_version_used | recorded string | 1 | measured |
| render_exit_code / seconds / timed_out | recorded | 1 attempt | measured |
| html_produced, html_sha256, html_bytes | recorded or null with reason | 1 attempt | measured |
| html_remote_reference_count | recorded | 1 HTML | measured |
| knitr_chunks_executed | recorded `n/21` | 21 chunks | measured (log) |
| test_pass_rate | pass/discovered, all pass | test_report_bundle + test_report | measured |
| outcome | `render_succeeded`, `render_blocked_final`, or `fix_invalid_no_attempt` | 1 | measured classification |
| cause_of_any_failure | text | n/a | inference, labelled |
| report_readability_acceptance | null | n/a | unknown (operator review) |
| listening_accepted | false | n/a | not claimed |

A successful render is a successful toolchain render only. It does not
establish listening quality, report readability, ~32 Hz fundamental presence,
note correctness, missed or extra notes, meter, or tone. The plain
`report.html` from `scripts/report.py` remains the primary report and the
fallback in every outcome. If the attempt fails, the outcome is
`render_blocked_final` per the ruling, and D6 closes on plain HTML.

## 6. Receipt `docs/agent-notes/sprints/20261007-s2r/quarto_fix-render-attempt.json`

Required keys:

- `schema_version`, `lane`, `sprint`, `linear`, `ruling` (operator ruling note
  plus R-N13), and `spec`, `spec_commit` and `implementation_commit`.
- `fix_applied`: the description, the `flake.nix` diff summary and the
  bundled-pandoc store path. If used, `fallback_used` with its URL and hash.
- `nix`: `eval_result`, `fetch_result` (`succeeded`, `failed` or `unknown`),
  `store_paths_copied` when visible, `builder` (local or remote),
  `flake_lock_sha256_before` and `flake_lock_sha256_after`, and the drvPaths
  before and after.
- `versions`: `quarto`, `pandoc`, `pandoc_path`, `r`.
- `preflight`: {`seconds`, `exit_code`, `syntax_highlighting_accepted`}.
- `attempt_count` (0 or 1), `command`, `started_utc`, `finished_utc`,
  `seconds`, `exit_code`, `timed_out`.
- `outcome` and `blocking_error_line` (null if none).
- `html_sha256`, `html_bytes`, `html_path` (gitignored),
  `remote_reference_scan`, `mathjax_present` and `project_config_merged`.
- `bundle`: {`path`, `bundle_sha256`, `verify_status`,
  `equals_prior_d6_bundle`}.
- `tests`: {`command`, `discovered`, `passed`, `failed`, `errors`, `skipped`}.
- `fallback_statement`: "The plain HTML report from scripts/report.py remains
  the primary report and the D6 fallback; this render is optional."
- `claims`: {`measurements`, `inferences`, `listening: []`}.
- **Explicit unknowns.** Each is null or false with a reason:
  `render_readability_acceptance: null`, `listening_accepted: false`,
  `fundamental_32hz_presence: null`, `note_correctness: null`,
  `missed_or_extra_notes: null` (no approved reference),
  `linux_report_shell_runtime: null` (only evaluated, not run, on Linux), and
  `project_config_merged`, which stays null if no HTML is produced.

`quarto_fix-handoff.json` lists files with sha256, test results, metrics,
unknowns and `root_owned_changes_requested`. The last is expected to be empty,
apart from an optional just-recipe suggestion.

## 7. Preregistration

Not applicable. The lane runs no comparative experiment: no arms, seeds, held
out data or scoring. The single render attempt's command, success
classification (`outcome` values above) and the no-retry rule are sealed in
this commit before the fix is written or run. Nothing in the protocol is tuned
after the attempt. No detector, profile, master or default is adopted or
changed.

## 8. Doctrine checks

This lane touches no audio processing. It adds no high-pass, notch or EQ, and
it does not change the ~32 Hz handling. The report is metadata-only, and the
bundle copies no media. Unknown and abstain fields from the bundle are rendered
as given and never filled in. Experimental non-improvement, meaning a failed
render, is a valid completion.
