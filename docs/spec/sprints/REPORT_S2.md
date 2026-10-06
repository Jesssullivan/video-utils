# S2 report_d6: hash-bound Quarto bundle and one bounded render attempt

Lane `report_d6`, sprint 20261006-s2, Linear TIN-5611. Branch
`sprint/20261006-s2/report_d6`, baseline `0cdca01`. Authority: the operator S2
sprint request, repository AGENTS.md, and R-HOOK-CONVERGENCE-20261004
(R-N11/R-N12/R-N13; TIN-3692 comment 98cf680c-7299-4949-bfb2-60079053ad43).
This document is the Phase 1 contract freeze. No numerics, no bundle build, no
nix evaluation and no render ran before this commit.

## Question and scope

The optional Quarto report (`reports/demo.qmd`) currently reads a full run
directory and re-derives lineage itself. This lane makes it consume a
**metadata-only, hash-bound bundle**. The bundle holds the manifest, bound
analysis, flags, markers and graph metadata, plus the merged S2 receipts. It
then makes **exactly one** operator-approved, bounded attempt to fetch the nix
`report` shell and render it. The standard-library HTML report
(`scripts/report.py`) stays the primary, always-available path. Its footer
sentence "not a Quarto-rendered report" is unchanged.

In scope:

- `scripts/report_bundle.py`, a stdlib-only CLI with `build`, `verify` and
  `describe`.
- `reports/demo.qmd` and `reports/plots.R`, rewritten to read the bundle with
  base R only.
- New files `reports/_quarto.yml` and `reports/.gitignore`.
- `tests/test_report_bundle.py`.
- The listening-review template.
- One real bundle build of the accepted FULLER run and one render attempt,
  each with a receipt.

Out of scope:

- Any change to `scripts/report.py` or `tests/test_report.py`.
- New audio processing, decoding, resampling, or FFmpeg invocation. The bundle
  never decodes media.
- Listening acceptance, and any detector, profile or master adoption.
- Note-correctness, missed-note or performance grading.
- Changes to `flake.nix` or `flake.lock`, the `just` recipes, `program/tools.json`,
  MCP/tool_api wiring, and skills. Requests for these go through
  `root_owned_changes_requested`.
- Repeated render retries, model downloads, daemons, and Linear writes.

## Owned files

| Path | Role |
| --- | --- |
| `scripts/report_bundle.py` | Bundle builder/verifier (stdlib only; reuses `scripts/report.py` helpers by import) |
| `tests/test_report_bundle.py` | >= 8 tests (planned 18 below) |
| `reports/demo.qmd`, `reports/plots.R` | Bundle-consuming Quarto report, base R only |
| `reports/_quarto.yml` | Project config: `embed-resources: true`, no remote assets |
| `reports/.gitignore` | Ignores in-tree render products (`.quarto/`, `_render/`, `*_files/`, `*.html`) |
| `docs/spec/sprints/REPORT_S2.md` | This contract |
| `docs/spec/examples/listening-review.json` | All-null operator listening-review template |
| `docs/agent-notes/sprints/20261006-s2/report_d6-*.json` | Contract, bundle-build, render-attempt and handoff receipts |

Outputs go under the gitignored
`/Users/jess/git/video-utils/.local/sprint2/report_d6/artifacts/s2/report_d6/`.

## Reuse (no duplication)

`report_bundle.py` imports `scripts/report.py` by path and uses its functions.
`load_json`, `sha256` and `strict_artifact` handle reading and safety.
`source_identity` and `analysis_lineage` bind the analysis to the run.
`auxiliary_evidence` handles dag/flags/markers freshness, including the
`program/instrument.json` external-context digest. The bundle does not
reimplement those rules. If `report.py` rejects something, the bundle rejects
it too.

## Bundle contract

### CLI (closed)

```
python3 scripts/report_bundle.py build --run-dir D [--analysis-run-dir A]
    [--annotation-store S] [--output-dir O]
python3 scripts/report_bundle.py verify --bundle-dir B [--check-origin] [--status-only]
python3 scripts/report_bundle.py describe
```

`--output-dir` defaults to
`artifacts/s2/report_d6/bundles/<run_id>-<UTCstamp>/` under the worktree root.
`verify --status-only` prints exactly one line: `verified` or
`refused:<reason>`. The Quarto document parses that line without jsonlite.
Exit codes: 0 means verified or built, 2 means refused, and 1 means an
unexpected error with only a class name (no paths, no private text).

### Inputs and binding rules

1. **Run.** `run_dir` must be an existing local directory with no `..` and no
   symlink component. Its `manifest.json` must be a non-empty object with
   `source.sha256` (64 hex) and an `output_sha256` mapping. Otherwise the
   build refuses with `manifest_missing`, `manifest_invalid` or
   `source_identity_missing`.
2. **Stage-file rehash (no copy).** Every file named in
   `manifest.output_sha256` that exists in `run_dir` is streamed through
   sha256 and compared. A mismatch refuses with `stage_hash_mismatch`. A
   listed file that is absent gets `absent` with a reason, which is not a
   refusal. Only names and hashes are recorded. The bytes never enter the
   bundle.
3. **Analysis run.** The build uses `run_dir/analysis.json` when it is
   present. Otherwise it uses `--analysis-run-dir`. Failing both, it derives
   `Path(manifest.capture_profile_application.authoring_dir).parents[1]`,
   which must contain `manifest.json`; this is the same basis `tone_ab` used.
   The basis is recorded as `run_local`, `explicit` or
   `parent_run_from_capture_profile_authoring_dir`. If the analysis-run
   manifest's `source.sha256` differs from the run's, the build refuses with
   `analysis_run_source_mismatch`.
4. **Analysis.** It is accepted only if
   `report.analysis_lineage(run_dir, run_manifest, analysis)` returns
   `original_source_hash_bound` or `verified_run_derivative_hash_bound`. That
   check rehashes the run's own derivative, for example `denoised.wav`. When
   `analysis.source_lineage.original_source_sha256` is present, it must also
   equal the run's source sha256. Otherwise the analysis is excluded, the
   status is recorded (for example `rejected_unrelated_or_modified_source`),
   and the report abstains. This is not a refusal.
5. **Auxiliary payloads.** `dag.json`, `flags.json` and `markers.json` from
   the analysis run go through `report.auxiliary_evidence(analysis_run_dir,
   analysis_run_manifest)`. Only `source_hash_bound` payloads are copied. In
   addition, if `dag.artifact_hashes["analysis.json"]` exists, it must equal
   the bound analysis sha256. Otherwise dag, flags and markers are excluded
   with `rejected_stale_analysis_binding`. `phrases.json` is copied only if
   `report.analysis_lineage` binds it the same way as rule 4. Rejected
   payloads stay visible as statuses.
6. **Events table.** `tables/events.csv` is derived from the bound
   `analysis.events` (columns `audio_relative_seconds`, `kind`). It is
   recorded as `role: derived_table` with `derived_from: analysis.json` and
   that file's sha256. The analysis run's own `events.csv` is not copied,
   because no hash binds it.
7. **S2 receipts (fixed registry, no directory scan).** These files are
   copied from the repo's `docs/agent-notes/sprints/20261006-s2/`:

   | Key | File | Binding class expected for the FULLER run |
   | --- | --- | --- |
   | `tone_ab` | `tone_ab-20261006T120702Z-actual-run.json` | `run_bound` (run.manifest_sha256 / run_id equal) |
   | `rhythm_clicks` | `rhythm_clicks-real-take.json` | `source_bound_different_analyzed_input` (analyzed cb8a3f... != run denoised 26c9f4...) |
   | `phrase_anchor_riff_spans` | `phrase_anchor_riff-real-take-spans.json` | `source_bound_*` (inputs.original_source_sha256 equal; per-anchor evidence sha recorded) |
   | `phrase_anchor_riff_bench` | `phrase_anchor_riff-heldout-score.json` | `synthetic_bank_not_take` |
   | `annot_corpus` | `annot_corpus-implementation.json` | `metadata_bound` (store manifest sha equals run manifest sha) |

   A missing registry file refuses with `receipt_missing`. A non-object JSON
   refuses with `receipt_invalid`. A receipt over 8 MiB refuses with
   `receipt_too_large`. Each receipt's sha256 is recorded. The binding class
   is computed only from hashes and IDs inside the receipt. It never comes
   from file names or mtimes. A receipt with no matching identity is
   `unbound_context_only` and is shown as such. The classes are
   `run_bound`, `source_bound_same_analyzed_input`,
   `source_bound_different_analyzed_input`, `metadata_bound`,
   `synthetic_bank_not_take` and `unbound_context_only`. The report shows
   receipt figures as each receipt's own measurements, with its claim class
   and binding class. They are not re-measured.
8. **Annotation store (operator corpus).** The store is optional. The
   default is the store referenced in the annot_corpus receipt
   (`artifacts/experiments/s1-demo-context-20261006T0627/review-annotations-v2.json`).
   It is bound only if `store.source_sha256` equals the run's source sha256
   and `store.manifest_sha256` equals the run's manifest sha256. Otherwise
   coverage is null with the reason `annotation_store_unbound` or
   `annotation_store_absent`. From the store the bundle copies only
   structured fields (`kind`, `basis`, `review_state`, `source_time_seconds`,
   `end_seconds`, `revision`, `id`). Free text is never copied.

### Bundle layout and hash binding

```
<bundle>/bundle.json            index (written last, atomically)
<bundle>/manifest.json          run manifest (copy)
<bundle>/analysis.json          if bound
<bundle>/dag.json|flags.json|markers.json|phrases.json   if bound
<bundle>/receipts/<key>.json    S2 registry receipts (copies)
<bundle>/annotations.json       structured projection of the bound store
<bundle>/tables/*.csv           derived base-R tables (members, receipts, corpus, unknowns, events, review flags <= 200 rows)
```

`bundle.json` holds a `members` list. Each entry has `bundle_path`, `role`,
`origin_path` (or `derived_from`), `origin_sha256`, `bundle_sha256`, `bytes`
and `binding_status`. For copies, origin and bundle sha256 are equal.
`bundle_sha256` is the sha256 of canonical JSON (`sort_keys`, separators
`,`/`:`, UTF-8) of `{run, members, receipts, unknowns}`. `verify` recomputes
every member hash and `bundle_sha256`. It refuses with
`member_hash_mismatch`, `member_missing`, `unexpected_member` (any file not
listed, except `bundle.json`) or `bundle_hash_mismatch`. With
`--check-origin` it also rehashes each origin and refuses with
`origin_changed` or `origin_missing`. The Quarto document always runs
`verify --status-only` before it shows any value.

### Safety: no audio, bounded, protected

- **No media in the bundle.** A member is refused (`media_member_refused`) if
  its extension is in {wav, flac, aiff, aif, mp3, aac, m4a, mov, mp4, m4v, mkv,
  webm, caf} (case-insensitive). It is also refused if its first 12 bytes
  match a RIFF/WAVE, `ftyp`, ID3, `fLaC`, `OggS`, `FORM`, `caff` or EBML magic.
  Limits are 8 MiB per member and 16 MiB in total (`bundle_too_large`). The
  bundle carries no URLs to media. It records `run_id` and file names only.
  Absolute `/Users/jess/Documents` paths in copied manifests remain as data in
  the gitignored bundle. The Quarto output never prints `source.path`.
- **Output directory.** It must be fresh (`output_dir_exists`). It is refused
  (`output_dir_protected`) if it resolves inside `run_dir`, the analysis-run
  directory, any `artifacts/runs/*`, `/Users/jess/Documents`,
  `/Users/jess/Desktop` or `.local/sprint1`. Work happens in
  `<output>.staging-<pid>` and is renamed into place only on success. A
  refusal before staging writes nothing. A failure after staging leaves only
  `<output>.failed/report-bundle.failed.json` with the reason.
- **Protected readback.** Before the build and after it, the builder records
  sha256, size and mtime_ns for every input file it opened in `run_dir`, the
  analysis-run directory, and the receipt and store paths. Any change gives
  the status `input_changed_during_build`. That is a refusal, and nothing is
  published.

### Explicit unknown/abstain fields (`bundle.json.unknowns`, each with a `reason`)

| Field | Value |
| --- | --- |
| `listening_accepted` | `false` |
| `listening_acceptance` | `"not_established"` |
| `operator_preference` | `null` |
| `perceived_fullness` | `null` |
| `nasal_quality` | `null` |
| `expected_rhythm_reference_approved` | `null` |
| `note_correctness` | `null` |
| `missed_or_extra_notes` | `null` |
| `performance_grade` | `"not_performed"` |
| `click_identity` | `"unverified"` |
| `physical_capture_latency` | `"uncalibrated"` |
| `meter` | `null` |
| `tonic` | `null` |
| `mode` | `null` |
| `fundamental_32hz_presence` | `null` |
| `room_response_recovered` | `false` |
| `stems` | `"not_produced"` |
| `editor_import_proven` | `false` |
| `default_adopted` | `false` |
| `master_changed` | `false` |
| `quarto_render_status` | `"not_attempted"` (the render receipt carries the outcome; the bundle is never rewritten) |

For `meter`, `tonic` and `mode`: a bound analysis or tonal payload may give
candidates. These are shown only as candidates, and the unknown stays null.

### Corpus coverage reported honestly

`bundle.json.corpus` keeps two pools apart. It never sums them.

- **`operator_labelled`** (class M on metadata) holds these fields:
  - `store_bound` (bool) and `annotation_count`.
  - `by_kind` and `by_basis`.
  - `covered_seconds` (the union of known extents) and `duration_seconds`
    (from `manifest.pcm`).
  - `coverage_fraction`.
  - `musical_phrase_labels` and `note_labels`.
  - `approved_expected_rhythm_reference: false`.

  Expected from current metadata (an inference until the build measures it):
  1 annotation, kind `noise`, basis INTENT, `needs_review`, extent 0-5 s. That
  gives 5.0 / 150.961111 s, about 3.3 %, with 0 phrase labels and 0 note
  labels. The report states this as "small labelled corpus: 1 operator
  annotation covering 5.0 of 150.96 s; 0 musical phrase or note labels".
  Absence of labels is not evidence of correctness.
- **`generated_banks`** (synthetic, class S): case counts and cohort names are
  copied from the phrase_anchor_riff held-out receipt. Each is labelled
  `origin: synthetic_generated_bank` with
  `real_take_accuracy: <receipt value>`. It is never presented as
  operator-labelled coverage.

## Quarto report contract

- `reports/_quarto.yml`: `project: {type: default, output-dir: _render}` and
  `format: html: {embed-resources: true, toc: true, html-math-method: plain}`.
  The document references no remote URLs.
- `reports/demo.qmd` takes `params.run_dir`, an absolute bundle path. It runs
  `python3 ../scripts/report_bundle.py verify --bundle-dir <run_dir>
  --status-only` through `system2`. On anything other than `verified`, it
  prints the refusal reason and shows no bundle values. It reads only
  `tables/*.csv` with base `read.csv`. `knitr::kable` is used when knitr is
  importable; otherwise the document falls back to `print`. The document
  needs no jsonlite.
- The document has these sections:
  1. Bundle identity: run_id, manifest/source/bundle sha256 prefixes, and
     analysis basis and lineage.
  2. Stage-file hash verification.
  3. S2 measured comparisons, as a receipt table with key, sha256 prefix,
     binding class, claim class and the headline figures. Figures are quoted
     from the receipt, not re-measured.
  4. Timing candidates (event plot).
  5. Review flags, as detector hypotheses distinct from user-reported
     annotations.
  6. Corpus coverage: operator-labelled versus generated banks.
  7. Unknowns.
  8. Listening review pointer to the all-null template.
- The existing text stays: no listening, source-recovery, meter or mistake
  claims. It says once that the plain `report.html` from `scripts/report.py`
  remains the primary report.
- `plots.R` takes `tables/events.csv` from the bundle and keeps the
  base-R-only plotting and the abstention messages.

## The one bounded render attempt (protocol frozen here)

Exactly one invocation, from the worktree root, after a successful bundle
build and verify, with the bundle path `B` absolute:

```
/usr/bin/time -p timeout 1800 nix develop .#report --command sh -c \
  'quarto --version; R --version | head -n 1; quarto render reports/demo.qmd -P run_dir="$1"' sh "$B"
```

The render step is the operator-approved
`quarto render reports/demo.qmd -P run_dir=<bundle>`. The version probes run
inside the same single `nix develop` invocation. This is not a second attempt.
stdout and stderr are captured to
`artifacts/s2/report_d6/render/attempt-1.log`. The receipt
`docs/agent-notes/sprints/20261006-s2/report_d6-render-attempt.json` records:

- `attempt_count: 1` and the command.
- `host`: `uname -m`, `sw_vers -productVersion`, `nix --version`, and that
  `nix` is the local-build-guard wrapper.
- `started_utc`, `finished_utc`, `seconds` and `exit_code`. Exit 124 means
  `timed_out`.
- `nix_fetch_evaluation`: `succeeded`, `failed` or `unknown`. It counts as
  succeeded only if the shell's command ran, meaning a version line was
  printed.
- `quarto_version` and `r_version`, or null with a reason.
- `outcome`: `rendered` or `render_blocked_on_host`.
- `blocking_error`: the exact last <= 4 KiB of stderr, verbatim.
- `html_sha256` and `html_bytes` for `reports/_render/demo.html`. That file is
  copied to `artifacts/s2/report_d6/render/demo.html`, and in-tree products
  are then removed.
- `remote_reference_scan`: counts of `http://` / `https://` in the HTML. This
  is information only.
- `bundle_sha256` and `verify_status` used.

On failure there is **no retry** and no flake edit, and the outcome is
`render_blocked_on_host`. A known risk, which is an inference: nixpkgs `pkgs.R`
may not include knitr/rmarkdown, and Quarto's knitr engine needs them. If that
is the error, the exact devShell change goes to `root_owned_changes_requested`.
That change is a `report` shell using
`(pkgs.rWrapper.override { packages = with pkgs.rPackages; [ knitr rmarkdown ]; })`
in place of `pkgs.R`. The host load is recorded with `uptime`, because wall
time reflects contention from other lanes.

## Completion metrics (denominators and claim classes)

Claim classes: M is a measurement on files or the host. S is synthetic test
behavior. I is an inference. L is listening, and stays pending. "Contract"
means a field or shape obligation.

| # | Metric | Denominator | Class |
| --- | --- | --- | --- |
| 1 | Bundle members whose bundle sha256 = origin sha256 (or derived_from hash recorded) and `verify --check-origin` = verified | n/n members of the FULLER bundle | M |
| 2 | Run stage files rehashed equal to `manifest.output_sha256` | 6/6 listed (baseline, cleaned, denoised, processed, residue, source) | M |
| 3 | Analysis binding | 1/1 with lineage `verified_run_derivative_hash_bound` via `parent_run_from_capture_profile_authoring_dir`, or an explicit rejection status | M |
| 4 | Auxiliary payload statuses recorded; bound payloads copied | 4/4 statuses (dag, flags, markers, phrases); bound k/4 | M |
| 5 | S2 registry receipts present, hashed, binding-classed | 5/5 | M (hash) + contract (class) |
| 6 | Media members in bundle | 0 of n members; total bytes <= 16 MiB | M |
| 7 | Protected readback unchanged | n/n opened input files (sha256/size/mtime) | M |
| 8 | Operator-labelled coverage reported separately from generated banks | covered_seconds / duration_seconds (expected 5.0/150.961), phrase labels 0, note labels 0; generated-bank cases with origin synthetic | M on metadata; S for banks |
| 9 | Unknown/abstain fields present with reasons | 21/21 | contract |
| 10 | `test_report_bundle` passing; `test_report` passing unchanged | >= 8 (planned 18); test_report all | M |
| 11 | Render attempts made | exactly 1/1, outcome `rendered` or `render_blocked_on_host`, versions/seconds/HTML sha256 or exact error | M (host) |
| 12 | HTML fallback intact | `scripts/report.py` byte-identical to baseline (sha256) and footer sentence present 1/1 | M |
| 13 | `listening-review.json` template leaves null | all non-schema leaves null (k/k) | contract |

Rendering success is not listening acceptance or report-readability acceptance.
A blocked render is a valid completion state if it is recorded with the exact
error.

## Test protocol

Run from the worktree root:

```
PYTHONPATH=tests python3 -m unittest test_report_bundle -v
PYTHONPATH=tests python3 -m unittest test_report -v    # directly affected (reused helpers); must pass unchanged
```

The fixtures are built in a temporary directory with the stdlib. A synthetic
run has a small `source.wav`/`denoised.wav`, written with `wave` (8 kHz mono,
0.5 s), and a manifest that sets `source.sha256` and `output_sha256`. A
parent analysis run has `capture-profiles/<id>/` and an `analysis.json`
whose `source.sha256` equals the denoised hash. The fixture also has a
dag/flags/markers trio whose hashes agree, fake S2 receipts carrying the
binding identities, and a v2 annotation store. The fixtures include no
FFmpeg, no network and no real media. Planned tests:

1. `test_build_hash_binds_every_member_and_bundle_sha`: verify gives `verified`; recomputing `bundle_sha256` matches.
2. `test_refuses_missing_or_invalid_manifest`: missing file, empty object and missing `source.sha256` each refuse and publish nothing.
3. `test_refuses_stage_hash_mismatch`: one byte flipped in `denoised.wav` gives `stage_hash_mismatch` and no output directory.
4. `test_parent_analysis_derived_from_authoring_dir`: basis `parent_run_from_capture_profile_authoring_dir`, lineage `verified_run_derivative_hash_bound`.
5. `test_unbound_analysis_abstains_not_refuses`: a different analyzed-input sha excludes analysis/flags/markers with status; the bundle still builds; unknowns are present.
6. `test_analysis_run_source_mismatch_refused`.
7. `test_stale_dag_analysis_hash_excludes_aux`: `dag.artifact_hashes["analysis.json"]` != the bound analysis gives `rejected_stale_analysis_binding`.
8. `test_verify_detects_tampered_member`: an edited bundle `analysis.json` gives `refused:member_hash_mismatch`; an extra file gives `refused:unexpected_member`.
9. `test_verify_check_origin_detects_changed_origin`: editing the origin manifest after the build gives `refused:origin_changed`.
10. `test_no_audio_or_video_bytes_in_bundle`: no member has a media extension or media magic. A registry entry pointing to a `.wav`, or RIFF bytes in a `.json`, gives `media_member_refused`. Size caps are enforced.
11. `test_receipt_missing_and_invalid_refused`.
12. `test_receipt_binding_classes`: the fixtures yield `run_bound`, `source_bound_different_analyzed_input`, `synthetic_bank_not_take`, `metadata_bound` and `unbound_context_only`.
13. `test_output_dir_fresh_and_protected`: an existing directory, a path inside run_dir, and a path inside an `artifacts/runs/*` lookalike are refused. A failure after staging leaves only `<output>.failed/report-bundle.failed.json`.
14. `test_protected_readback_and_change_during_build`: inputs are unchanged after the build. An input mutated via an injected hook gives `input_changed_during_build`, and nothing is published.
15. `test_corpus_coverage_operator_vs_generated`: one noise annotation over 0-5 s gives coverage 5/duration with phrase and note labels at 0. Generated banks are separate. An unbound store gives null with a reason. Free text is never copied.
16. `test_unknown_fields_complete_with_reasons`: all 21 fields with the exact values.
17. `test_listening_review_template_all_null`: loads `docs/spec/examples/listening-review.json`; every leaf except `schema_id`/`schema_version` is null.
18. `test_quarto_sources_contract_and_html_fallback_intact`: `demo.qmd` uses `params$run_dir` and calls `report_bundle.py verify --status-only`, with no `jsonlite` and no `http(s)://`. `_quarto.yml` sets `embed-resources: true`. `scripts/report.py` still contains "not a Quarto-rendered report".

The lane does not run the full suite. Root does that.

## Execution plan after the freeze

- **Phase 2.** Implement and test. Then run one real `build` on
  `artifacts/runs/20261006T041633Z-990aa1bd6737`. This involves streamed
  hashing of about 140 MB of WAV only, with no decoding and a 600 s timeout.
  Then run `verify --check-origin` and write
  `report_d6-bundle-build.json`.
- **Phase 3.** Make the single render attempt above and write
  `report_d6-render-attempt.json`. This is at most one heavy job.
- **Phase 4.** Write the handoff `report_d6-handoff.json`. It holds file
  hashes, test counts, metrics against the denominators, and
  `root_owned_changes_requested`. Expected requests are a `just report-bundle`
  recipe, a typed tool descriptor and skill if root admits the bundle as a
  primitive, and the flake R-package change if the render was blocked on it.

## Preregistration

This lane runs **no experiment**: no arms, no tuned parameters, and no truth or
held-out scoring. So no preregistration applies. The render protocol, the
receipt registry, the binding classes, the size caps and the unknown-field list
are fixed by this commit and are not changed after the build or render
outcome is seen. Non-improvement, abstention or a blocked render are valid
outcomes.

Receipt: `report_d6 | spec only, no numerics/no nix/no render | Phase 1
contract freeze | R-N13 (R-HOOK-CONVERGENCE-20261004) | accepted run
20261006T041633Z-990aa1bd6737 read-only | no default/profile/master adoption`.
