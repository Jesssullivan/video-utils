# S2 annot_corpus lane: annotation markers, flags triage, coverage-first corpus evaluation

Status: **Phase 1 contract freeze** (no numerics run). Sprint `20261006-s2`, Linear
TIN-5604 (related TIN-5489, TIN-5548; peer delivery V3/V5 on TIN-5186 is posted by root).
Authority: the operator's S2 request, repository `AGENTS.md`, and
R-HOOK-CONVERGENCE-20261004 / R-N11 / R-N12 / R-N13. Owner: lane `annot_corpus`
(branch `sprint/20261006-s2/annot_corpus`). Root signs merges, admits MCP hooks and
skills, edits `program/*`, `scripts/tool_api.py`, `just/*`, and writes Linear.

This lane adds three **read-only projections** over existing artifacts. It adds no
flag kind, no detector, no default profile/master, no annotation write path and no
musical verdict. Experimental non-improvement or a null metric is a valid result.

## Owned files

| Path | Role |
| --- | --- |
| `scripts/annotation_markers.py` | v2 store → generic marker JSON/CSV projection |
| `scripts/flags_triage.py` | `flags.json` → `flags-triage.json` default review view |
| `scripts/corpus_eval_s2.py` | coverage-first evaluation of untouched detector proposals against the sparse operator corpus |
| `tests/test_annotation_markers.py`, `tests/test_flags_triage.py`, `tests/test_corpus_eval_s2.py` | owner tests |
| `docs/spec/ANNOTATION_V2_VOCABULARY.md` | 11 kinds × 4 bases × 3 states reference |
| `docs/spec/sprints/ANNOT_CORPUS_S2.md` | this contract |
| `docs/spec/examples/corpus-split/operator-review-corpus.json` | example split manifest (metadata only) |
| `docs/agent-notes/peers/xoruby/V3-corpus-split-receipt.json` | real `validate_split(summary=True)` receipt |
| `docs/agent-notes/peers/xoruby/V5-vocabulary-mapping.md` | v2 → xoruby `noul`/unknown mapping |
| `docs/agent-notes/sprints/20261006-s2/annot_corpus-*.json` | dated lane receipts |

Generated outputs go only to `.local/sprint2/annot_corpus/artifacts/s2/annot_corpus/`
(gitignored). Accepted run directories under `artifacts/runs/*` and
`artifacts/experiments/*` are read, never written. The original take in
`~/Documents` is never opened by this lane (all inputs are existing JSON metadata).

## Reused interfaces (no second ontology)

- `annotation_v2`: `KINDS`, `BASES`, `STATES`, `LABELS`, `validate_store`,
  `read_bytes`, `parse_json`, `AnnotationError`. Kind/basis/state are never
  reclassified; `claim_label` and `musical_verdict` pass through unchanged.
- `corpus`: `source_bounds`, `source_identity`, `Metadata` (bounded nonblocking
  dirfd reader); `corpus_split_s1.validate_split` (full mode for the evaluator,
  `summary=True` for V3).
- `markers.COLUMNS` (`source_time_seconds, end_seconds, name, confidence, status,
  evidence`) and `dag.sha256` / `dag.atomic_write`.
- `marked_video.select_markers` / `compose_callouts` are imported **read-only in
  tests only** to prove consumability; `marked_video.py` is not modified.
- `marked_video.COMPARISON_KINDS`, `LABELS` for the flag tier table (imported, not copied).

## 1. `scripts/annotation_markers.py`

CLI: `python3 scripts/annotation_markers.py RUN_DIR --store-sha256 HEX --output-dir DIR [--include-text]`.
Callable: `project(run_dir, *, expected_store_sha256, include_text=False) -> (payload: dict, csv_text: str)`.

Inputs: run-local `manifest.json` and `review-annotations-v2.json` (the only path
pair `corpus_split_s1` admits). Refusals (stable codes, nothing written):
`stale_annotation_store` (store bytes ≠ `--store-sha256`), `annotation_manifest_mismatch`
/ `annotation_source_mismatch` / `annotation_provenance_manifest_mismatch`
(delegated to `validate_store`), `source_timeline_required` (delegated clocks),
`annotation_file_changed_during_read`, `output_inside_run_dir`. Both store forms are
accepted: full (with `replay_receipts`) and public GET projection (`public=True`).

Output `annotation-markers.json`:

- `schema_id: "video-utils.annotation-markers.s2"`, `format: "generic_review_markers_seconds"`,
  `source_sha256`, `manifest_sha256`, `store_sha256`, `store_revision`,
  `timeline.axis: "original_source_stream_timestamps_seconds"`.
- `markers`: visible rows; `suppressed_markers`: rows with `suppression_reason`.
  Each row has exactly `markers.COLUMNS` plus `basis_label`, `display_label`,
  `label_basis`, `annotation_id`, `kind`, `basis`, `review_state`, `extent_known`,
  `musical_verdict: "not_established"`, `performance_issue_confirmed: false`.
  - `name` = v2 `kind` verbatim; `status` = v2 review state verbatim.
  - `confidence` = `"not_applicable_human_annotation"` for operator bases,
    `"unknown_uncalibrated"` for `detector_hypothesis`/`reference_comparison`.
  - `basis_label` = `annotation_v2.LABELS[basis]` (USER REPORTED / INTENT / REVIEW /
    REFERENCE REVIEW); `display_label` = `"<basis_label>: <kind>"`; `label_basis` = basis.
  - `evidence` = `{annotation_id, basis, claim_label, operator_certainty, candidate_id,
    reference_sha256, extent_known, text_included}`. `note`/`operator_quote` are
    included verbatim only with `--include-text` (default omitted: markers are a
    shareable interchange and V6 privacy wording is still held by the operator).
  - Points (`extent_known: false`) keep `end_seconds == source_time_seconds`; no
    duration is invented.
- `counts`: `record_count`, `visible_count`, `suppressed_count`,
  `suppressed_by_reason` (dict), with `visible_count + suppressed_count == record_count`.
- `picture_coverage: "not_evaluated"`, `editor_import: "not_validated"`,
  `listening_acceptance: "not_established"`.

CSV `annotation-markers.csv` header is exactly `markers.COLUMNS + ["basis_label"]`;
`evidence` is JSON-encoded as in `markers.py`. Only visible rows are written.

Visibility rule (frozen): (a) `dismissed_candidate` → suppressed,
`dismissed_candidate_state`. (b) Remaining rows sorted by basis priority
`operator_assertion` > `reference_comparison` > `detector_hypothesis` >
`operator_context`, then start, then `annotation_id`; a row is suppressed with
`exceeds_two_visible_callouts` if, at any instant of its interval, two
higher-priority visible rows are already active (matches the compact overlay's
"at most two issue callouts" and `marked_video` `visible_lines_maximum: 2`). For
overlap only, a point uses the same 1.0 s presentation dwell as `marked_video`;
the dwell is never written as duration. User-reported rows therefore cannot be
hidden by detector rows.

Known limitation (root-owned, not changed here): in `arrangement_labels=True`
mode, `marked_video.arrangement_display` badges every non-arrangement row as
"Timing review"; in default mode it shows "Review candidate". Neither shows the
basis label. Rendering basis badges needs a root-owned `marked_video` change; the
lane records the request instead of editing it.

## 2. `scripts/flags_triage.py`

CLI: `python3 scripts/flags_triage.py RUN_DIR --output PATH`. Callable:
`triage(run_dir) -> dict`. Output `flags-triage.json` refuses a path inside `RUN_DIR`.

Inputs: `RUN_DIR/flags.json`; window basis from (1) `phrases.json`
`interpretation.semantic_phrases` **only when** it is a non-empty list of objects
with finite source start/end (hash-bound by `dag.json` `artifact_hashes` when a DAG
is present), else (2) the click grid of `flags.evidence_artifacts.clicks` (selector
file sha256 must equal the binding; `click_grid.period_seconds` finite > 0;
`phase_seconds_audio_relative` finite) mapped to source seconds via
`flags.timeline.audio_start_seconds`. Windows are 16 consecutive grid periods:
`window = floor((t - phase_source) / (16 * period))`. Feature segments
(`observations.segment_candidates`, `proposed_review_spans`) are **not** phrase
spans: they are themselves texture/region flags and cannot define their own
triage windows. If neither basis is available: refuse `triage_window_basis_unavailable`
(no invented window). Other refusals: `flags_source_mismatch`, `stale_click_grid`,
`invalid_flag_interval`.

A flag is assigned to the window containing its `source_time_seconds`
(`crosses_window_boundary` recorded). In phrase-span mode, a flag outside every
span goes to one residual window `unspanned`.

Navigation proxies (hidden by default, retained verbatim in `hidden_navigation`):
`kind == "four_pulse_group_review_candidate"` or `confidence ==
"navigation_proxy_not_confirmed_bar"` or `evidence.kind == "four_pulse_bar_proxy"`.

Priority rule `flags-triage-priority-v1` (lexicographic, deterministic):

1. Tier by existing kind (no new kinds):
   T1 within-take comparison differences = `marked_video.COMPARISON_KINDS`
   (`recurrence_relative_alignment_shift_review`, `recurrence_relative_rate_difference_review`,
   `recurrence_motif_timing_difference_review`, `recurrence_attack_density_difference_review`);
   T2 `automatic_recurrence_review_candidate`;
   T3 `low_register_riff_or_breakdown_candidate`, `bright_ending_texture_candidate`;
   T4 `spectral_texture_region_candidate`;
   T5 any other kind (`unranked_kind`, kept eligible, never dropped).
2. Flags with a hash-bound `selected_evidence_slot` before those without.
3. Earlier `source_time_seconds`; then `kind`; then original flag index.

Numeric `confidence`/`similarity` values are **not** used: they are documented as
uncalibrated, not probabilities. One winner per window goes to `shown`; the rest
go to `suppressed` with `reason: "lower_priority_in_window"` and `winner_flag_id`.
Every item carries `flag_index`, `flag_id` (`flag-%04d-` + first 12 hex of the
canonical flag sha256, the `marked_video` convention), `window_id`, `tier`, and
the original flag unchanged under `flag`.

`denominators`: `total_flags`, `navigation_hidden`, `suppressed_lower_priority`,
`shown`, `window_count`, `windows_with_shown`; invariant
`shown + suppressed_lower_priority + navigation_hidden == total_flags`.
Header fields: `schema_id: "video-utils.flags-triage.s2"`, `source_sha256`,
`flags_sha256`, `window_basis` (`phrase_spans` | `click_grid_16_period_navigation_windows`,
artifact selector+sha256, period, phase, `bar_or_downbeat_identified: false`),
`priority_rule` (the table above, verbatim), `view: "default_review_ordering_not_verdict"`,
`performance_grade: "not_assigned"`, `musical_verdict: "not_established"`. Generated
strings contain no verdict vocabulary (`mistake`, `error`, `wrong`, `missed`,
`incorrect`, `confirmed`); copied original flag text is left untouched.

## 3. `scripts/corpus_eval_s2.py`

CLI: `python3 scripts/corpus_eval_s2.py evaluate SPLIT_MANIFEST --root ROOT --proposals FLAGS_JSON --proposals-sha256 HEX --output PATH`.
Callable: `evaluate(split_manifest, *, local_root, proposals_path, proposals_sha256) -> dict`.

Validation first: `corpus_split_s1.validate_split(..., summary=False)` (refusals
propagate unchanged). Proposals bytes must hash to `--proposals-sha256`
(`stale_proposals`); they are read once and never modified, filtered, re-thresholded
or re-ranked ("untouched detector proposals"). Navigation proxies are excluded
from proposals by the triage rule above and counted (`navigation_excluded`).

Per record with selected annotations, in this order:

1. **Clock alignment** `clock_alignment_status`:
   `source_mismatch` (proposal `source_sha256` ≠ record source) → all metrics null;
   `clock_unknown` (manifest clocks fail `corpus.source_bounds` or proposal
   `timeline.axis` ≠ original source axis) → null; otherwise
   `same_source_original_clock_declared`. Always also
   `detector_latency: "uncalibrated"` and `proposal_lineage_differs_from_annotation_manifest`
   (bool: the proposal run's manifest is not the annotation store's manifest).
2. **Coverage**: `covered_seconds` = measure of the union of selected spans with
   `extent_known: true` and basis in {`operator_assertion`, `operator_context`,
   `reference_comparison`}; points add 0 s. `total_seconds` = source duration from
   `corpus.source_bounds`. `coverage_fraction = covered/total`. Coverage is the
   reviewer-attended region only; it is never treated as reviewed absence.
3. **Metrics** with fixed threshold `coverage_threshold = 0.5`:
   - coverage below threshold → `precision: null`, `recall: null`,
     `reason: "coverage_below_threshold"`.
   - `recall` = matched labelled positives / labelled positives (numerator and
     denominator reported) only if coverage ≥ threshold and positives ≥ 1, else null
     (`no_labelled_positives`). Labelled positive = `operator_assertion`,
     state `accepted_observation`, literal quote present (the V5 "labelled" rule).
   - `precision` is **always null** in S2 with
     `reason: "false_positive_requires_reviewed_absence_label"`: the v2 schema has
     no reviewed-absence label and unlabelled time is `unknown_not_negative`.
   - Matching: a proposal matches a labelled span if their source intervals
     intersect; a point (either side) uses ±0.25 s (the existing
     `motif_match_window_maximum_seconds`), one-to-one, earliest-first.
   - `negatives`, `true_negatives`, `false_positives` are always `null`.
4. **Axes**, kept as separate fields, each `{labelled_positive_count, eligible,
   precision, recall, reason}`:
   - `error_axes`: `timing` (`rhythm_timing`, `rhythm_pattern`), `omission`
     (`phrase_omission`), `duration` (`phrase_duration`), `pitch` (`melodic_pitch`).
   - `articulation_axes`: `palm_mute`, `legato`, `tapping`, `sweep`, `rest`, `chord`.
     `rest_execution` counts toward `rest`. v2 `articulation` has no subtype, so
     it goes to `articulation_unspecified` and is **not** spread across the six
     axes; the six axes stay `unknown` with `reason: "no_subtype_in_v2_schema"` and
     `detector_for_axis: "none"` (no current flag kind identifies technique).
   - `not_scored_kinds`: `meter_mismatch`, `tone`, `noise`, `other` with reasons
     (context/capture, not performance-error axes).
   - Pitch axis carries `reference_required: true`; no note-correctness or
     missed-note statement is produced.

Header: `schema_id: "video-utils.corpus-eval.s2"`, split manifest sha256, group
receipts from `validate_split`, `proposals_sha256`, `coverage_threshold`,
`match_tolerance_seconds`, `negatives_inferred: 0`, `unlabelled_intervals:
"unknown_not_negative"`, `ground_truth_established: false`,
`listening_acceptance: "not_established"`, `source_audio_read: false`.

## 4. Documents

- `docs/spec/ANNOTATION_V2_VOCABULARY.md`: all 11 kinds × 4 bases × 3 states (132
  schema-legal combinations), required authorship/quote/certainty per basis, saved
  labels, the fixed `musical_verdict`, and the evaluator axis of each kind.
- `docs/agent-notes/peers/xoruby/V5-vocabulary-mapping.md`: `operator_assertion`
  + `accepted_observation` + literal quote → labelled record (certainty carried);
  `needs_review` (ambiguous) → `unknown`; `dismissed_candidate` → `unknown`
  (dismissing a hypothesis is not reviewed absence); `detector_hypothesis`,
  `operator_context`, `reference_comparison` → `unknown` for class labels
  (context/reference hash carried); unlabelled → `unknown`, **never absent**.
  xoruby's exact token spelling (`noul`) is as relayed by the peer and remains
  to be confirmed by them.
- `docs/spec/examples/corpus-split/operator-review-corpus.json`: one
  `real_recording`, `unassigned` record for source
  `a522115f…76c6`, manifest
  `artifacts/experiments/s1-demo-context-20261006T0627/manifest.json`
  (`61c9b393…0a5f`, the accepted FULLER run manifest), one v2 annotation ref
  (store `17041cb3…eca`, revision 1, selected `e2add83c-3d08-485b-a79f-2d9f0405f025`),
  and context ref `program/demo-arrangement.json` (`170a33eb…541a`, `operator_context`).
- `docs/agent-notes/peers/xoruby/V3-corpus-split-receipt.json`: produced by
  `validate_split(summary=True)` against a staging root
  `artifacts/s2/annot_corpus/v3-root/` holding **byte-identical copies** (sha256
  verified before and after) of the example manifest and the three metadata files
  at the same relative paths. No audio file is copied or opened. Root can
  reproduce it with `--root` = repository root after merge.

## Completion metrics (with denominators and claim classes)

Claim classes: **M** = measurement on existing artifacts; **S** = synthetic
fixture behavior; **I** = inference; **L** = listening claim (none made here).

1. (S) Annotation projection: CSV header equals `markers.COLUMNS + ["basis_label"]`;
   stale store hash and manifest mismatch refuse with zero bytes written;
   `visible_count + suppressed_count == record_count` with reasons; projected rows
   pass `marked_video.select_markers` and `compose_callouts` in both label modes
   without modifying `marked_video.py` (file sha256 unchanged).
2. (M) Real S1 store projection: 1/1 record projected (`INTENT`, 0–5 s, not
   dismissed) with store `17041cb3…` and manifest `61c9b393…`; text omitted by default.
3. (S) Triage: at most one shown per window over a seeded 200-case property loop;
   `shown + suppressed + hidden == total`; navigation proxies never shown and all
   retained; confidence permutation leaves `shown` unchanged; no new kinds; no
   verdict wording in generated strings.
4. (M) Real-take triage on `artifacts/runs/20261006T034521Z-a0def0c43eac/flags.json`
   (sha256 `95a0106c…a732`, 171 flags): report `shown/171`, `navigation_hidden/171`
   (expected 112 from kind counts), `suppressed/171`, `window_count`. Acceptance:
   `shown ≤ 30`. (I) Preregistered arithmetic expectation: click-grid basis (the run
   has no list-valued `semantic_phrases`), window 16 × ≈0.676 s ≈ 10.8 s over
   ≈151 s → ≤ 15 windows → `shown ≤ 15`. The test asserts the rule invariants,
   not this number.
5. (S) Evaluator: coverage union arithmetic; below-threshold → P/R null with
   reason; above-threshold synthetic recall carries numerator/denominator;
   precision always null with reason; unlabelled proposals in uncovered time do
   not change any number; `source_mismatch` / `clock_unknown` null all metrics;
   proposals bytes unchanged.
6. (M) Real corpus evaluation (example manifest × 171 untouched flags):
   `covered_seconds = 5.0`, `total_seconds` from the manifest bounds (≈150.96),
   `coverage_fraction ≈ 0.033 < 0.5` → precision/recall null,
   `labelled_positive_count = 0` on every axis (the one record is `operator_context`).
   This is the expected null result, not a detector failure.
7. (M) V3 receipt is the verbatim `validate_split(summary=True)` output, with
   staging hash verification recorded in a lane receipt.
8. ≥ 18 owner tests pass (minimum 14 required); exact counts and commit sha
   recorded in `annot_corpus-*.json` receipts.

## Test protocol

Run from the worktree root, owned modules only:

```
PYTHONPATH=tests python3 -m unittest test_annotation_markers test_flags_triage test_corpus_eval_s2 -v
```

Directly affected modules (read-only imports): `test_annotation_v2`,
`test_corpus_split_s1`, `test_markers` if present. The full suite is root's.

Fixtures: synthetic only, built in `tempfile.TemporaryDirectory()` from
`annotation_v2` structures (fresh random-free UUIDs from `uuid.uuid5` over fixed
names), synthetic manifests with explicit clocks (including a negative-origin case),
synthetic `flags.json`/`clicks.json`/`phrases.json` with known kinds, and seeded
property loops (`random.Random(20261006)`, 200 cases). Real-artifact tests are
`skipUnless` the main-checkout artifacts exist, open only JSON metadata, and
assert invariants plus recorded hashes. No FFmpeg, audio decode or model.

Planned tests (≥ 18):

- `test_annotation_markers`: columns/CSV header; basis label per basis;
  stale store refusal writes nothing; manifest mismatch refusal; dismissed
  suppression and count identity; >2 concurrent overlap suppression keeps user
  reports; point keeps zero extent; `marked_video` consumability both modes and
  unchanged file hash; text omitted by default / literal with flag; output inside
  run dir refused.
- `test_flags_triage`: proxies hidden and retained; one-per-window property;
  tier/tiebreak order; phrase-span vs click-grid basis and unspanned residual;
  basis-unavailable / stale clicks / source mismatch refusals; confidence
  permutation invariance; no new kinds / no verdict words; real-take invariants (skip if absent).
- `test_corpus_eval_s2`: coverage union; below-threshold nulls; synthetic recall
  with numerator/denominator and precision null; uncovered proposals do not change
  numbers; axes separation and unspecified articulation; operator_context not
  positive; clock statuses; proposals untouched; real-take null result (skip if
  absent); V3 receipt equals a fresh `validate_split(summary=True)` on the staged
  root; V5 doc contains the three mapping rules.

## Unknown and abstain fields the outputs must carry

`musical_verdict: "not_established"`, `performance_issue_confirmed: false`,
`listening_acceptance: "not_established"`, `performance_grade: "not_assigned"`,
`ground_truth_established: false`, `picture_coverage: "not_evaluated"`,
`editor_import: "not_validated"`, `bar_or_downbeat_identified: false`,
`detector_latency: "uncalibrated"`, `unlabelled_intervals: "unknown_not_negative"`,
`negatives_inferred: 0`, `precision: null` (+reason), `recall: null` (+reason when
applicable), `negatives/true_negatives/false_positives: null`, per-axis
`unknown` with reasons, tempo/meter/tonic as found (null stays null), and
`confidence: "unknown_uncalibrated"` where no calibrated value exists.

## Preregistration (sealed at this commit, before running anything)

This lane runs deterministic projections, not a model comparison; there is one
arm and no tuning.

- Fixed inputs (sha256): proposals `artifacts/runs/20261006T034521Z-a0def0c43eac/flags.json`
  `95a0106c84a338ddc756f3c17879e5eccf8966b4344fe6326b71da7872e8a732`; its run
  manifest `a6c371ab36e1f50b850f167a42b010ffa7b923b32aca14f4bfd70fb24036077c`;
  annotation store `artifacts/experiments/s1-demo-context-20261006T0627/review-annotations-v2.json`
  `17041cb31476f91409e3c48f6434fcde8874ecd175a221b0f3fe644614d40eca`; annotation
  manifest (FULLER run) `61c9b3930c36d050818901138eb1820d5dc940e3603d38f019bde793da750a5f`;
  context `program/demo-arrangement.json` `170a33eb9e5832cbc0a3309c6041b5ded06f5fc1265ba519a6633ab0f84e541a`;
  source `a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.
- Arms: one (untouched proposals). No alternative thresholds, windows, tiers or
  matching tolerances will be tried on the real take.
- Frozen constants: `coverage_threshold = 0.5`, `match_tolerance_seconds = 0.25`,
  window = 16 grid periods, priority rule v1, visible callout limit 2, seed
  `20261006`, 200 property cases.
- Truth: the operator corpus is already known (one `operator_context` record,
  0–5 s); predicted outcome is metric 6 (null P/R, coverage ≈ 0.033). There is no
  held-out set to protect; if a second take arrives (operator: by 2026-10-09) it is
  evaluated with these frozen constants or a new preregistration.
- If the real-take shown count exceeds 30, the result is reported as a failed
  acceptance with the measured count; the rule is not retuned in this sprint.

## Root-owned follow-ups (requested, not made)

- `marked_video` basis-aware badge for annotation markers (see limitation in §1).
- MCP hooks/skills and `program/tools.json` entries for the three projections,
  if root admits them; until then they are experimental lane helpers.
