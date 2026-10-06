# S1 corpus split validation and readiness

Authority: the operator's five-hour, six-agent sprint; root sprint
`20261006-S1.md`; R-HOOK-CONVERGENCE-20261004, R-N12/R-N13. Lane TIN-5566.
Owner files are `scripts/corpus_split_s1.py`, `tests/test_corpus_split_s1.py`,
this specification and `corpus-*` sprint receipts. The existing version-1
corpus validator, actual annotation stores and original/accepted media are
unchanged. Root owns MCP admission, skill, recipe, merge and publication.

## Intent and closed interface

Validate explicitly authored metadata and a split assignment. Group all declared
derivatives and annotation references of a take so they cannot leak between
train, validation and test. No assignment randomization, training, audio reads,
inference, source rehash, network, annotation writes or tool installation occurs.
Source identity, parentage and reviewer authorship remain supplied assertions.
Omitted/forged lineage with entirely different supplied identities cannot be
authenticated by a metadata-only tool.

CLI:

```sh
python3 scripts/corpus_split_s1.py validate MANIFEST --root LOCAL_ROOT --summary
```

`--summary` is optional for direct CLI; the MCP hook must request it. Stdout is
one bounded JSON success receipt, exit 0. Refusal is one structured stderr JSON
`{"status":"rejected","error":"code"}`, exit 1. Missing required CLI arguments
use argparse's normal exit 2. Callable:
`validate_split(manifest_path, local_root=ROOT, summary=False) -> dict` raises
`corpus.CorpusError` for validated refusals. No write or output-path argument
exists. Root's outer typed process timeout bounds the operation.

The manifest is a closed object with exactly:

- `schema_id: "video-utils.corpus-split.s1"`, integer `schema_version: 1`;
- `corpus_id`: existing bounded ASCII identifier; positive integer `revision`;
- `coverage: "sparse_or_unknown_no_negative_inference"`;
- `approval_state: "unreviewed"` (a validated split is not corpus acceptance);
- `records`: 1–500 records; `context_refs`: 0–32 references.

Each record has exactly `id`, `take_family_id`, `split`, `origin`,
`source_sha256`, `artifact_sha256`, `parent_ids`, `augmentation_group_ids`,
`manifest`, `annotation_refs`. IDs follow the existing 1–80-character ASCII
identifier contract. Split is `train|validation|test|unassigned`; origin is
`real_recording|synthetic_fixture`. Hashes are lowercase SHA256. Original-source
and artifact identity are distinct; an original may use the same supplied hash
for both. Parent IDs and augmentation group IDs are unique lists of at most32.
Every parent must occur in this manifest and use the same original source hash.
Self-parentage and directed cycles are refused.

`manifest` is null for an original metadata draft with no labels, or exactly
`{"path":"relative/manifest.json","sha256":"..."}`. When provided, the bytes,
original source and known timeline bounds are checked with existing corpus v1
helpers. `annotation_refs` is 0–8 references per record, each exactly
`store:{path,sha256}`, `schema_version:1|2`, nonnegative integer `revision`,
`selected_ids` (unique strings, at most200). A non-null run manifest is required
for any annotation reference, including an empty selected list. All referenced
stored annotations are validated before selection; unselected invalid entries
are not bypassed. Hashes and revisions are checked even for empty selections.

Version1 stores must be run-local `review-annotations.json`; validation delegates
to `corpus.annotations` and `corpus.verify_annotation_receipt` unchanged.
Version2 stores must be run-local `review-annotations-v2.json`; validation
delegates to the annotation owner's pure `annotation_v2.validate_store(...)`
with pinned source, manifest and bounds. No second annotation taxonomy is
defined. Kind, basis, status, certainty, spans, authorship, quote and provenance
are retained unchanged in full output. The S1 annotation module must be
integrated before v2 references are admitted; until then these references fail
explicitly with `annotation_v2_validator_unavailable`.
Both versions additionally delegate the existing candidate artifact/source/event
receipt check for every stored item. Stale marker/flag bytes, a foreign candidate
source or a candidate ID absent from the current hash-bound metadata refuses the
corpus; a valid pure v2 store alone is insufficient candidate provenance.

Each context reference has exactly `metadata:{path,sha256}`, `source_sha256`,
`basis:"operator_context"`. Referenced JSON must contain the same source hash
and that source must occur in the corpus. It is byte-bound context, never a
label/negative/example of detected musical correctness. The saved demo draft
references `program/demo-arrangement.json` as context only. Its approximate
10–11-second first-phrase anchor and 404 expected clicks retain their original
operator-intent status. No time spans or detections are manufactured from it.

## Grouping and split refusal

Union all rows connected by a declared take family, original source hash,
artifact hash, parent edge, augmentation group, annotation store hash, or selected
annotation UUID plus original source. A connected group may have at most one
assigned split. `unassigned` remains a distinct row state; it can share a group
with an assigned member without being silently assigned itself. A group with no
assigned member returns `assigned_split:null`.

Conflicting family IDs or origins in a connected group are refused, rather than
silently accepting relabelled identities. A shared artifact cannot claim two
different original sources. This catches a forged family label when the original
source/artifact/parent/augmentation is still declared. A entirely fabricated,
unlinked identity cannot be proved false by metadata validation.

Group receipts contain sorted record IDs, supplied family ID, assigned split,
unassigned row count, and a SHA256 key over sorted IDs/source/artifact hashes and
sorted parent/augmentation lists. The key is stable under input order and a
consistent whole-family split change; content or declared lineage changes alter
it. It is an evaluation grouping receipt, not a proof of audio authorship.

## Coverage, counts and bounded output

The full result preserves records and selected annotation payloads. The summary
retains group/source metadata identities, origin/split counts, referenced and
unique selected annotation counts and context hash receipts. It omits selected
annotation text, quotes, identities and local paths. It does not skip validation.
Record count and referenced-label count are not unique take/label denominators;
the receipt reports `group_count` and `unique_selected_annotation_count`
separately. Repeated selected UUIDs from the same original source count once in
the latter. Sparse coverage stays sparse; unlabelled intervals are
`unknown_not_negative`, `absence_denominator:0`, `negative_examples_inferred:0`.
This sprint does not admit explicit negative-example labels.

Every success retains `ground_truth_established:false`,
`listening_acceptance:"not_established"`, `source_audio_read:false`,
`training_performed:false`, `approval_state:"unreviewed"` and explicit supplied
identity/authorship boundaries. Annotation `accepted_observation` is never a
musician-correctness verdict.

Limits: 1MB per JSON, 16MB total unique metadata bytes, 500 records, 1,000 total
annotation references, 5,000 selected annotation references, 32 parents and32
augmentation IDs per record, 32 contexts, 200 stored/selected annotations per
store, 12-hour known source duration, 1MB result including newline. Full output
that would exceed the limit refuses with `result_output_limit`; summary can
succeed after complete validation. Input reads reuse the existing nonblocking
dirfd reader: reject traversal, symlinks, nonregular files/FIFOs, duplicate JSON
keys, invalid UTF8, nonfinite constants, changed files, stale hashes and unsafe
paths. JSON limits bound Unicode payloads as bytes, not only characters.

## Read-only evaluation readiness

The saved `corpus-readiness.json` hashes the existing numerical pitch report and
independent audit, then projects their already recorded native-window metrics.
It is metadata review only: no model launch, activation decode, new metric
calculation or actual-take inference. The report identifies C1 missing-F0 native
stable-monophonic fundamental matches34/426 and octave errors392/426. Chroma
matches426/426 do not establish correct low-register notes. Native stable absence
has denominator0 and false-voicing rate null. Ladder, transitions and polyphony
do not become additional native stable-monophonic samples. These failure and
coverage boundaries remain readiness blockers for real-note grading.

The original-only demo draft is unassigned and unreviewed with zero selected
annotations; it establishes no real heldout accuracy and no negative coverage.
A reviewer-authored source-bound corpus and disjoint take families are needed
before claiming real evaluation readiness. Synthetic split/refusal property
success proves metadata behavior only.
