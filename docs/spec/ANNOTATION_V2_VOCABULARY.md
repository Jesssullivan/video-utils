# Annotation v2 vocabulary: kinds, bases, states

Reference for consumers of `review-annotations-v2.json` (schema owner:
`scripts/annotation_v2.py`; storage semantics: `docs/spec/sprints/ANNOTATIONS_S1.md`).
This page restates the closed vocabulary and records how S2 read-only projections
(`scripts/annotation_markers.py`, `scripts/corpus_eval_s2.py`) treat each value.
It defines no new kind, basis, state or label; the validator is authoritative.

## Size of the vocabulary

11 kinds × 4 bases × 3 states = **132 schema-legal combinations**. The validator
does not restrict which kind may pair with which basis or state; it restricts
authorship, quote, certainty and reference hash by basis (table below). Every
saved record also carries `claim_label` (= the basis label) and the fixed
`musical_verdict: "not_established"`.

## Kinds (11) and S2 evaluator axis

| Kind | Evaluator field | Axis | Notes |
| --- | --- | --- | --- |
| `rhythm_timing` | `error_axes` | `timing` | kind-agnostic overlap; no flag kind identifies timing type |
| `rhythm_pattern` | `error_axes` | `timing` | same as above |
| `phrase_omission` | `error_axes` | `omission` | no omission verdict is produced without an approved reference |
| `phrase_duration` | `error_axes` | `duration` | |
| `melodic_pitch` | `error_axes` | `pitch` | `reference_required: true`; `note_correctness: "not_established"` |
| `articulation` | `articulation_unspecified` | none of the six | v2 has no subtype; never spread across palm_mute/legato/tapping/sweep/rest/chord |
| `rest_execution` | `articulation_axes` | `rest` | only kind that maps to a named articulation axis |
| `meter_mismatch` | `not_scored_kinds` | — | meter context, not a performance axis |
| `tone` | `not_scored_kinds` | — | tone/capture context |
| `noise` | `not_scored_kinds` | — | capture-noise context (the S1 real record is `noise` / `operator_context`) |
| `other` | `not_scored_kinds` | — | unclassified |

Articulation axes `palm_mute`, `legato`, `tapping`, `sweep`, `chord` have no v2
kind; they are reported as `status: "unknown"`, `reason: "no_subtype_in_v2_schema"`,
`detector_for_axis: "none"`, with `labelled_positive_count: 0` meaning "no record
can carry this label", not "no such technique occurred".

## Bases (4)

| Basis | Required authorship | `operator_quote` / `operator_certainty` | Other | Saved label (`LABELS`) | Marker `confidence` |
| --- | --- | --- | --- | --- | --- |
| `operator_assertion` | actor `operator` (via browser/agent/cli) | literal nonempty quote; `uncertain` or `confirmed` | | `USER REPORTED` | `not_applicable_human_annotation` |
| `operator_context` | actor `operator` | both null | | `INTENT` | `not_applicable_human_annotation` |
| `detector_hypothesis` | actor `detector` | both null | | `REVIEW` | `unknown_uncalibrated` |
| `reference_comparison` | actor `operator`, `agent` or `detector` | both null | `reference_sha256` required | `REFERENCE REVIEW` | `unknown_uncalibrated` |

`operator_certainty: confirmed` records the reviewer's own certainty; it does not
change `musical_verdict`, which stays `not_established`.

## States (3)

`needs_review`, `accepted_observation`, `dismissed_candidate`.

## Basis × state treatment in S2 projections (applies to every kind)

| Basis | State | Marker projection | Coverage (extent known) | Labelled positive |
| --- | --- | --- | --- | --- |
| `operator_assertion` | `needs_review` | visible (priority 1) | yes | no (ambiguous → unknown) |
| `operator_assertion` | `accepted_observation` | visible (priority 1) | yes | **yes** (literal quote is mandatory for this basis) |
| `operator_assertion` | `dismissed_candidate` | suppressed `dismissed_candidate_state` | yes | no |
| `reference_comparison` | `needs_review` | visible (priority 2) | yes | no |
| `reference_comparison` | `accepted_observation` | visible (priority 2) | yes | no |
| `reference_comparison` | `dismissed_candidate` | suppressed | yes | no |
| `detector_hypothesis` | `needs_review` | visible (priority 3) | no | no |
| `detector_hypothesis` | `accepted_observation` | visible (priority 3) | no | no |
| `detector_hypothesis` | `dismissed_candidate` | suppressed | no | no |
| `operator_context` | `needs_review` | visible (priority 4) | yes | no |
| `operator_context` | `accepted_observation` | visible (priority 4) | yes | no |
| `operator_context` | `dismissed_candidate` | suppressed | yes | no |

"Visible (priority n)" is subject to the two-concurrent-callout limit: a row is
suppressed with `exceeds_two_visible_callouts` only if two earlier-ordered visible
rows are active at some instant of its interval, so `USER REPORTED` rows can never
be hidden by detector or context rows. Points (`extent_known: false`) add 0 s of
coverage and keep `end_seconds == source_time_seconds` in markers.

Coverage means reviewer-attended time, not reviewed absence. The v2 schema has no
reviewed-absence label, so unlabelled time is `unknown_not_negative` and precision
is always null with `false_positive_requires_reviewed_absence_label`.

## Peer interchange

The xoruby mapping (labelled record / `unknown`, never absent) is recorded in
`docs/agent-notes/peers/xoruby/V5-vocabulary-mapping.md`.
