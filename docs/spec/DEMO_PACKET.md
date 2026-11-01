# Demo packet known limits

Linear: TIN-7788. Authority: the narrate seat's visibletext lane brief. A demo packet is the private run record a
producer hands to the Cade DAG, so it stays out of this repository. This file holds the limits every packet carries.
A producer's `docs/demo/<slug>/README.md` copies the open rows.

## Open limits

| Limit | Effect | What holds today | Closes when |
| --- | --- | --- | --- |
| The BS-21 name list reads no text a slide, plot, clip or deck shows. Only the intake's `nv` denylist reads it | A name must be on that denylist for a slide to refuse it. A name only on `claimsDenylist` passes on screen | `producer_review: pending_operator`, the `visible_text` gate and the operator reading each slide | video-utils `feat/tin-7788-nv-visible-text-subject-20261031` and cade `feat/tin-7788-bs21-shown-text-20261031` have both landed. The root then removes this row |

## Limits that stay

| Limit | Why |
| --- | --- |
| Text burned into a frame, or a text source that differs from its picture, passes every check | No check reads pixels or runs OCR. The digest binds the file, not its match to the picture |
| A paraphrase or a translation of a name passes | No denylist entry spells it |
