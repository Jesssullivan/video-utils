---
name: guitar-corpus-eval
description: Evaluate sha256-pinned untouched guitar detector proposals against a validated sparse operator annotation corpus, reporting coverage first, clock alignment, recall only above 0.5 coverage, precision always null and separate error/articulation axes; never infers negatives.
---

# Coverage-first sparse corpus evaluation

Hook `corpus_eval_s2`; prompt `guitar-corpus-eval`. The worker is `scripts/corpus_eval_s2.py`; operators run `just corpus-eval-s2 MANIFEST PROPOSALS PROPOSALS_SHA256 OUTPUT [LOCAL_ROOT]`. Read [the frozen contract, section 3](../../../docs/spec/sprints/ANNOT_CORPUS_S2.md) and [the split contract](../../../docs/spec/sprints/CORPUS_S1.md).

**Intent.** Ask how much of each take a reviewer actually attended and, only where that coverage is sufficient, how many literal operator-asserted issues an untouched detector proposal set overlaps. Absence of a label is unknown, not a negative.

**Knobs.** Required `manifest`, `proposals`, `proposals_sha256` and `output`; optional `local_root` (defaults to the repository, as for `corpus_split`) and `timeout_seconds` (1–900, default 120). The evaluation constants are fixed, not knobs: `coverage_threshold` 0.5 and match tolerance 0.25 s (the existing motif match window).

**Paths.** The manifest stays inside `local_root`; traversal and symlink components reject. `proposals` is an existing regular flags JSON of at most 20 MB, pinned by `proposals_sha256`; a changed file refuses with `stale_proposals`. `output` must be a fresh `.json` file beneath repository `artifacts/`, with an existing parent, not beside the proposals file. No audio is read and nothing else is written.

**Dependencies.** Validate the split with `corpus_split` and review the selected v2 stores with `annotation_v2` first. Pin the exact proposals file you intend to evaluate. Proposals are read once and never filtered, re-thresholded or re-ranked; only navigation proxies are excluded, and they are counted.

**Evidence.** Each record reports clock alignment first (`source_mismatch` or `clock_unknown` nulls every metric; detector latency stays `uncalibrated`), then coverage of selected spans with known extent. Below 0.5 coverage, or with no labelled positives, recall is null, and that null is a valid result. A labelled positive is an `operator_assertion` in state `accepted_observation` with a literal quote. Precision is always null (`false_positive_requires_reviewed_absence_label`), and negatives, true negatives and false positives are null. Error axes (timing, omission, duration, pitch) and articulation axes (palm mute, legato, tapping, sweep, rest, chord) stay separate. v2 `articulation` has no subtype, so it is reported as `articulation_unspecified` and never spread across technique axes. The pitch axis requires a reference and makes no note-correctness or missed-note statement.

**Research and iteration.** Compare one untouched proposal set at a time into fresh outputs, and report coverage and denominators before any recall. The nine-string C1 low end, heavy distortion, tapping and legato make detector timing ambiguous; do not tune proposals toward the sparse labels or treat a recall number as ground truth. `ground_truth_established` stays false and `listening_acceptance` stays `not_established`. Record the manifest hash, proposals hash and output hash in the owning receipt.
