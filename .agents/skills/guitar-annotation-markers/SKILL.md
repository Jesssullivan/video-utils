---
name: guitar-annotation-markers
description: Project a sha256-pinned structured guitar annotation store into shareable source-timed marker JSON/CSV whose basis labels keep user reports, operator intent, reviews and reference reviews distinct from detector hypotheses; no verdict, no editor import.
---

# Share structured practice annotations as markers

Hook `annotation_markers`; prompt `guitar-annotation-markers`. The worker is `scripts/annotation_markers.py`; operators run `just annotation-markers RUN_DIR STORE_SHA256 OUTPUT_DIR`. Read [the frozen contract, section 1](../../../docs/spec/sprints/ANNOT_CORPUS_S2.md) and [the v2 vocabulary](../../../docs/spec/ANNOTATION_V2_VOCABULARY.md) before interpreting a row.

**Intent.** Turn the musician's structured v2 annotations (rushed fills, phrase omissions, palm-mute or tapping notes, tone or fan-noise context) into generic markers that a band can open next to the restored clip, without promoting any row into a verdict.

**Knobs.** Required `run_dir`, `store_sha256` (exact lowercase hex of the current `review-annotations-v2.json` bytes) and `output_dir`; optional `include_text` (default `false`) and `timeout_seconds` (1–900, default 120). The store pin is the freshness guard: a changed or stale store refuses with `stale_annotation_store`, so read the store first and pin what you read. `include_text: true` copies `note` and `operator_quote` verbatim into marker evidence; leave it off for shareable output unless the operator has said that the free text may leave the run.

**Paths.** `run_dir` must hold regular `manifest.json` and `review-annotations-v2.json`; traversal, URL and symlink components reject, and relative paths resolve from the repository root. `output_dir` must be a fresh directory beneath repository `artifacts/`, with an existing parent and outside `run_dir`. The hook never writes the run or the store and never overwrites an earlier projection.

**Dependencies.** Run `annotation_v2` (read) first to get the current revision and hash. This tool does not create, edit or reconcile annotations.

**Evidence.** Each row keeps `name` = v2 kind and `status` = v2 review state verbatim, with `basis_label` USER REPORTED / INTENT / REVIEW / REFERENCE REVIEW. These labels state who asserted a row; they are not verdicts. Every row carries `musical_verdict: not_established` and `performance_issue_confirmed: false`. Human bases get `confidence: not_applicable_human_annotation`; detector or reference rows stay `unknown_uncalibrated`. Points keep `end_seconds == source_time_seconds`; no phrase duration is invented. At most two callouts are visible at once by the frozen basis priority (`operator_assertion` > `reference_comparison` > `detector_hypothesis` > `operator_context`), so detector rows cannot hide a user report. Suppressed rows stay in `suppressed_markers` with a reason, and `visible_count + suppressed_count == record_count`.

**Limits.** `editor_import` is `not_validated`, `picture_coverage` is `not_evaluated` and `listening_acceptance` is `not_established`. The existing `marked_video` overlay does not yet draw the basis badge (a deferred root change), so do not claim that a rendered preview distinguishes user reports from detector hypotheses.

**Iteration.** After a store revision changes, re-read the store, pin the new hash and project into a fresh directory. Compare visible and suppressed counts and suppression reasons across revisions. Never edit rows to change visibility. Distorted nine-string playing near 32 Hz, palm mutes, rests, tuplets, tapping, sweeps and legato make onsets ambiguous; a marker time is the annotator's span, not a measured attack. Record the store hash, output hashes and any `include_text` decision in the owning receipt.
