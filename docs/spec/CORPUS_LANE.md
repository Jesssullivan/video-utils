# Local annotation corpus

Authority: operator ten-hour parallel goal, graph-integration checkpoint;
R-HOOK-CONVERGENCE-20261004, R-N12/R-N13. Owner `repo_patterns` owns only
`scripts/corpus.py`, `tests/test_corpus.py` and this document. Root owns any
Just, MCP, skill, report or publication integration.

## Definition of done, before implementation

Provide a standard-library, read-only validator for an explicitly authored local
corpus manifest. Bind selected labels to existing review annotation UUIDs,
original-source hashes, exact source-time spans, reviewer identities, review-store
revisions and byte hashes. Require explicit seconds units and sparse coverage.
Keep ambiguous labels and overlapping observations; never infer negative labels
from unlabelled intervals. Separate real recordings from generated fixtures in
the result, and never call either verified musician ground truth.

Validate existing metadata only: no media decoding, source audio reads, downloads,
models, installations, subprocesses, server or annotation writes. Reject stale
receipts, source/span mismatches, missing attribution, wrong units, duplicate IDs,
unsafe paths, malformed/oversized JSON and changed files. Test independent failure
scenarios and a successful sparse, ambiguous, nonzero-origin synthetic review
fixture. Leave actual-take annotations unchanged. Record commands, results and
limits here before handoff.

## Manifest and command contract

`python3 scripts/corpus.py validate MANIFEST [--root LOCAL_ROOT]` prints a JSON
receipt or a structured error and exits nonzero. The default root is this
repository. Both the manifest and all referenced metadata must be regular files
inside that root; metadata paths are relative to the root, with no symlink
components or traversal. `--root` is an explicit local corpus boundary, useful
for isolated fixtures. It grants no network or audio access.

Add `--summary` to receive a compact receipt after **complete** validation,
including every selected label and candidate receipt. Default full JSON output
remains unchanged. The summary emits compact JSON and has a 1,000,000-byte
ceiling including the final newline; unusually large aggregate receipts fail
with `summary_output_limit` rather than truncation. No validation ceiling changes.

Summary top fields: `schema_version`, `status`, `result_mode: metadata_summary`,
`corpus_id`, `corpus_revision`, `corpus_sha256`, `units`, `coverage`,
`reviewer_count`, `source_count`, `label_count`, `source_origin_counts`,
`source_origin_label_counts`, `metadata_bytes_read`, `sources`,
`source_audio_read: false`, `ground_truth_established: false`,
`listening_acceptance: not_established`, `unlabelled_intervals`,
`assertion_boundary` and `synthetic_labels`. At most 100 source rows contain only
`id`, `origin`, `source_sha256`, `manifest_sha256`, `annotation_store_sha256`,
`annotation_revision`, `source_bounds_seconds`, `label_count`,
`certainty_counts` (`observation`, `ambiguous`) and `review_status_counts`
(`needs_review`, `accepted_observation`, `dismissed_candidate`). No raw labels,
notes, reviewer identities or local paths appear in this projection. Both
origin-count objects always include real-recording and synthetic-fixture keys;
origin and authorship remain supplied assertions in either output mode.

Schema version 1 requires `corpus_id`, positive integer `revision`,
`units: source_seconds`, `coverage: sparse_reviewed_spans`, a reviewer list, and
a source list. Each reviewer has a unique `id` and supplied `identity` text.
Each source has a unique `id`, explicit `origin` (`real_recording` or
`synthetic_fixture`), `source_sha256`, a `manifest` receipt (`path`, `sha256`),
an `annotations` receipt (`path`, `sha256`, `revision`), and `labels`.

Each selected label has `annotation_id`, `reviewer_id`, UTC `reviewed_at`,
`source_start_seconds`, `source_end_seconds`, bounded `label` text,
`certainty` (`observation` or `ambiguous`) and `alternatives` (a bounded list of
possible label strings, permitted only for ambiguous labels). Spans must exactly
match the selected stored annotation and lie within the run's original timeline.
An observation requires an `accepted_observation` review state; ambiguous and
dismissed candidates remain review observations and never become confirmed
performance errors. Empty label lists are valid; they contribute no negatives.

The annotation store must be the run-local `review-annotations.json` beside its
`manifest.json`. Its schema, source hash, revision and
`listening_acceptance: not_established` must match. A selected annotation's most
recent `updated_with` receipt (or legacy `created_with` when absent) must bind to
the current run-manifest hash. If its candidate-artifact hash is non-null, verify
the matching run-local `markers.json` or `flags.json` bytes and source hash.
Historical annotations whose receipt changed require an explicit fresh review;
validation does not silently rebind them.

For candidate-bound annotations, the candidate UUID-like fingerprint must also
match an event identity in the hashed markers/flags receipt, using the existing
review worker's source hash, kind and source-span convention. Manual notes may
have no candidate ID. No consensus vote or automatic label is added.

Resource ceilings: 1 MB per JSON file, 16 MB total referenced JSON bytes, 100
sources, 100 reviewers, 200 stored annotations per source, 5,000 selected labels,
eight alternatives per ambiguous label, and 12 hours per source. No source audio
bytes are opened or rehashed. Source identity, source origin, reviewer identity
and label authorship remain supplied assertions; metadata hashes and consistency
are checked facts. Verification cannot establish who listened or that a musical
label is correct. No new audio tool is advertised by this lane.

## Completed checkpoint and receipt

Followup definition of done, before implementation: add opt-in `--summary` for
the parent's typed metadata hook. Run the identical complete validation first,
then project a compact aggregate receipt with at most 100 source rows and no
labels, notes, reviewer identities or local paths. Retain original CLI output
by default and all validation rejection behavior. Check compact-output size,
complete-validation errors and unchanged metadata bytes. This followup owns
only the same three corpus files; tool/skill owners integrate independently.

The validator and focused tests are implemented. Command:
`python3 -m unittest discover -s tests -p test_corpus.py -v`.
Initial result: 13 tests passed on the local macOS host with Python 3.12.14. Coverage
includes sparse/overlapping ambiguous spans, separate declared source origins,
nonzero source origins, exact span/units checks, source and byte-hash provenance,
stale revisions and historical manifests, changed/foreign candidates, missing
review attribution, UTC/review chronology, duplicate labels, malformed JSON,
duplicate JSON keys, nonfinite values, byte ceilings, symlink components,
traversal, external manifests and nonblocking rejection of FIFOs.

An integration test invokes the existing `review_server.py annotate` command on
isolated fictional metadata and validates its actual saved store without schema
translation. The corpus CLI succeeds on that source-bound fixture and reports
structured rejection on a changed span. Read-only tests compare referenced file
bytes before and after validation. All test metadata explicitly describes
fixtures; no actual recording, actual-take annotation or model was opened,
downloaded or labelled. This establishes local metadata validation behavior,
not label accuracy, listening acceptance, corpus authenticity or audio quality.

Receipt: `repo_patterns | three named corpus files and isolated test fixtures |
authorized graph-integration corpus validator | R-N12/R-N13,
R-HOOK-CONVERGENCE-20261004 | no corpus validator or corpus labels for actual take |
implemented; 13 focused tests passed; no remote mutation or background service`.
No new recipe, MCP operation, tool registry entry, training job or report claim
was added. Root owns further integration and publication.

Followup result: 16 focused tests pass with the compact summary implemented.
The summary and full CLI reject the same stale hashes, invalid spans and wrong
units; byte comparisons confirm no metadata writes. A valid sub-1MB corpus with
2,560 fictional labels expands its full receipt past the MCP dispatcher's 2MiB
output ceiling because candidate paths repeat. The actual summary CLI fully
validates that fixture and returns fewer than 5,000 bytes, with all 2,560 labels
counted, source hashes/revisions retained, and no labels or paths disclosed.
The generated fixture respects macOS path limits and is removed after the test.
Root separately authorizes the twentieth typed metadata hook and its skill;
this lane's followup changes only its three named corpus files.
