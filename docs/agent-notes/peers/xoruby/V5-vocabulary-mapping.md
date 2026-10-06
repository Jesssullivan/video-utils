# V5: video-utils annotation v2 → xoruby label mapping

Date: 2026-10-06. Sprint `20261006-s2`, lane `annot_corpus`, Linear TIN-5604
(peer delivery on TIN-5186 is posted by root). Source vocabulary:
`docs/spec/ANNOTATION_V2_VOCABULARY.md` (schema owner `scripts/annotation_v2.py`).

## Mapping rules (normative for this interchange)

1. **observation with literal reviewer assertion -> labelled record.**
   `basis: operator_assertion` + `status: accepted_observation` + a literal
   nonempty `operator_quote` becomes a labelled xoruby record. `kind` passes
   through verbatim as the class; `operator_certainty` (`uncertain`/`confirmed`)
   is carried as reported certainty, not as a calibrated probability.
2. **ambiguous -> unknown.** `status: needs_review` (any basis) maps to xoruby
   `unknown`.
3. **dismissed -> unknown.** `status: dismissed_candidate` maps to `unknown`:
   dismissing a hypothesis is not a reviewed absence.
4. **non-assertion bases -> unknown for class labels.** `detector_hypothesis`,
   `operator_context` and `reference_comparison` map to `unknown` for class
   labels. Context is carried as context; a `reference_comparison` carries its
   `reference_sha256`.
5. **unlabelled -> unknown never absent.** Time with no selected record maps to
   `unknown`. No negative, absent or "clean" label is ever emitted, because v2 has
   no reviewed-absence label (`unlabelled_intervals: unknown_not_negative`,
   `negatives_inferred: 0`).

Summary line for the peer: observation with literal reviewer assertion -> labelled record; ambiguous -> unknown; unlabelled -> unknown never absent.

## Token spelling

xoruby's unlabelled/negative-safe token was relayed as `noul`; its exact
spelling and whether `noul` and `unknown` are distinct tokens on the xoruby side
remain **to be confirmed by the peer**. Until confirmed, this side emits the
literal `unknown` and treats `noul` as its relayed alias.

## Fields carried on every mapped record

`source_sha256`, `manifest_sha256`, store sha256 and revision, `annotation_id`,
source-second span with `extent_known` (points stay points), `basis`,
`claim_label`, `musical_verdict: "not_established"`. Note and quote text are
not carried by default (operator privacy wording for shares is still held).

## Current real corpus (measured)

One selected record on source `a522115f…76c6`: `noise` / `operator_context` /
`needs_review`, 0–5 s. Under the rules above it maps to `unknown` (context).
There are 0 labelled records; precision and recall on this corpus are null by
construction (coverage 5.0 / 150.961111 s ≈ 0.033 < 0.5).

## Limitations

- Actor fields are reported provenance, not authenticated identity.
- No note-correctness, missed-note or musical-verdict claim is transmitted.
- Articulation subtypes (palm mute, legato, tapping, sweep, chord) are not
  representable in v2 and stay `unknown`; `rest_execution` maps to rest.
