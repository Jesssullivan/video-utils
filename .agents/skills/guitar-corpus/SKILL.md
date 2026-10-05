---
name: guitar-corpus
description: Validate bounded local guitar annotation-corpus metadata and provenance while retaining sparse coverage, ambiguity and supplied reviewer assertions; do not establish audio or musician ground truth.
---

# Validate a sparse annotation corpus

**Hook:** MCP tool `corpus` and MCP prompt `guitar-corpus`; inspect `tools/list` for publication status and the current schema. The standard-library metadata validator is implemented. Its operation is validation only, with no audio read/decode, annotation write, server, training, model download or network access.

## Use and controls

Use `corpus` with required `manifest`, optional `local_root` (default repository boundary), and `timeout_seconds` (integer 1–900, default 600). Manifest/root strings are bounded to 1–4,096 characters. Recipe fallback: `just tool-run corpus '{"manifest":"<root>/corpus.json","local_root":"<root>"}'`. Direct worker: `python3 scripts/corpus.py validate "<manifest>" [--root "<local-root>"] [--summary]`. No operation selector, media control or model knob is exposed.

The hook always requests `--summary`: all selected metadata and labels are validated before projecting compact hash/count/span receipts. The summary omits label text, notes and reviewer identities while retaining origin, certainty and review-state counts plus explicit assertion boundaries. Full direct-CLI output remains available without `--summary`; neither output mode changes validation or establishes musical truth.

Read [the corpus manifest/receipt contract](../../../docs/spec/CORPUS_LANE.md). The manifest and referenced metadata must be regular files inside the explicit local root. Metadata paths are root-relative and reject traversal/symlink components. Preserve unsafe-path rejection; do not silently normalize, relocate or rebind references to make a failed validation pass.

Inspect the explicitly authored version-1 manifest: corpus ID/revision, `units: source_seconds`, `coverage: sparse_reviewed_spans`, supplied reviewer identities, declared `real_recording|synthetic_fixture` origins, source hashes, run/store byte receipts and selected annotation UUIDs. Selected labels need reviewer ID, UTC review time, exact saved source-time span, `observation|ambiguous` certainty and any ambiguous alternatives. An observation requires an accepted-observation review state; that state is not a correctness verdict.

## Provenance, sparse coverage and assertions

The validator checks metadata byte hashes, run-local source/store identity, revisions, source-time bounds, current annotation manifest receipts and optional candidate artifact/event fingerprints. It never opens or rehashes source audio. Report checked metadata consistency separately from supplied audio identity, source origin, reviewer identity and label authorship. A receipt cannot establish who listened or that a label accurately describes the performance.

Keep ambiguous alternatives and overlapping observations. Unlabelled intervals and empty label lists contribute no negative examples. Generated reference fixtures remain explicitly `synthetic_fixture`; their labels never become real-recording ground truth. No consensus vote, inferred musician intent or automatic label is added.

Stale revisions, old manifest/candidate receipts or mismatched spans require reconciliation and, where applicable, an explicit fresh review. Validation does not change the annotation store. Do not invent attribution, claim a review occurred, drop uncertainty or blindly recompute historical hashes. Preserve `listening_acceptance: not_established` and `ground_truth_established:false`.

Resource ceilings are 1 MB per JSON, 16 MB referenced JSON total, 100 sources/reviewers, 200 stored annotations per source, 5,000 selected labels, eight alternatives per ambiguous label and twelve hours per source. Inspect counts, source-origin separation, metadata receipts and assertion-boundary fields before reporting success. Validation failure is a specific metadata finding, not an audio-quality judgment.

## Guitar-specific interpretation and iteration

Near-32 Hz fundamentals, distorted harmonics, nine-string custom tuning, rests, tuplets, palm mutes, tapping and legato make performance labels context-sensitive. Tuning metadata or a detected transient does not prove an intended note or mistake. This tool validates how reviewer observations are attributed and bound, not their musical truth.

**Review scenario:** A few reviewed phrase spans cannot label the rest of a take correct. A synthetic expected-rhythm fixture cannot establish the player's intended real rhythm. Preserve those boundaries even when all metadata receipts validate.

Inspect the intended corpus and current receipts, run bounded validation, explain any specific inconsistency, and repeat only after an explicitly supplied metadata/review correction. Research schema/units/provenance in the actual contract and worker; root/manifest/timeout settings only change validation boundaries, not interpretation. Follow [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for evidence handling. Record outcomes through the owning lane's durable receipt; do not read audio or launch training to strengthen a metadata claim.
