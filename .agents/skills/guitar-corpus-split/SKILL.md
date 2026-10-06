---
name: guitar-corpus-split
description: Validate explicit guitar take-family corpus splits and source-bound annotation metadata, rejecting derivative leakage while preserving sparse coverage and unknown labels; no training or audio analysis.
---

# Keep held-out takes independent

Hook `corpus_split`; prompt `guitar-corpus-split`. Inspect the current catalog and read [the implemented split contract](../../../docs/spec/sprints/CORPUS_S1.md). This is read-only metadata validation, not a dataset generator, random split selector or classifier.

Use required `manifest`, optional existing `local_root` (repository default), and bounded `timeout_seconds`. The hook requests the compact summary after full validation. All referenced regular JSON stays inside the selected root; traversal and symlink components reject. Direct CLI full output may contain declared notes; the MCP summary omits annotation content and reporter identities.

Inspect explicit take-family, original source and artifact identities, parent and augmentation links, assigned `train|validation|test|unassigned` splits, origins, current manifest/store hashes and annotation revisions. Any connected family across assigned splits is leakage, including republished annotations or derived files. Correct the authored grouping rather than dropping a link to make validation pass. No source audio is opened or rehashed; recorded audio hashes and authorship remain supplied claims.

Sparse reviewed spans leave the rest unknown. No labels means no negative examples; absence denominator0 is valid. Operator arrangement context is intent, not detected boundaries or correctness. Generated fixtures remain synthetic and never become real take ground truth. Keep the fixed nine-string tuning and existing C1 octave failures in evaluation readiness; successful metadata validation cannot resolve those pitch errors.

The manifest is explicitly unreviewed. Retain `ground_truth_established:false`, listening not established and training not performed even after validation. Limits include500 records,1MB perJSON,16MB aggregate metadata and5000 selected annotations. Unknowns and exclusions belong in the reported denominator.

Identify the intended corpus and held-out family boundary, validate once, explain the precise inconsistency if rejected, then rerun only after an authorized metadata correction. Preserve earlier receipts and do not silently refresh stale stores or manufacture reviewer labels. No model acquisition, inference, service launch or master adoption follows from this tool.
