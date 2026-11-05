# Demo packet known limits

Linear: TIN-7788. Authority: the narrate seat's lane brief, receipt on TIN-7788 comment `e6e6330d`. A demo packet is
the private run record a producer hands to the Cade DAG, so it stays out of this repository. This file holds the limits
a packet carries. The producer's demo README, `docs/demo/<slug>/README.md` in its own private repository, copies the
open rows and cites this file for the limits that stay. That copy is a manual step, and no check reads the README.

## Open limits

| Limit | Effect | What holds today | Closes when |
| --- | --- | --- | --- |
| The BS-21 name list reads no text a slide, plot, clip or deck shows on a DAG without the guard step. J168 stops the registration hook from forcing that step, so this holds by ruling. The hand-off worker from cade#250 reads each source's raw bytes, and it reads them on a running DAG only after a worker binding and a declaration exist. The intake's `nv` denylist reads only a shown PNG or MP4 with a text source, and only when a denylist runs. Nothing reads a deck's text | On such a DAG a name must be on that denylist for a slide to refuse it. A name only on the BS-21 name list reaches the screen | No machine gate catches a read slide. The `visible_text` gate holds only an unread or opaque asset, and it reads `passed` for a read slide. `producer_review: pending_operator` is a label no code reads. What remains is the operator's own read of each slide, and no gate records that read. A `listening` acceptance records a GO on the cut, with no record of a slide read | The November 30 audit decides whether the registration hook forces the guard step again. Until then the root keeps this row |

## Limits that stay

| Limit | Why |
| --- | --- |
| Text burned into a frame that the asset's text source does not list, or a text source that differs from its picture, passes every machine check | No check reads pixels or runs OCR. The digest binds the file, not its match to the picture. On a guarded intake an asset with no text source is `unread`, and it waits at the operator. Since video-utils#84 and cade#259 landed, a JSON source with an empty list, or a list of only whitespace or zero-width text, is `opaque` and waits there too. Without a guarded intake the `visible_text` gate reads `not_applicable`, so nothing waits |
| A paraphrase or a translation passes, in any letters | No denylist entry spells it. J168 stops the `script` class on every bundle, `never_name` included |

## J168 removal

J168 (TIN-7125 `9738d494`) removes the BS-21 and `ip_private` code refusals for go-live, with a revisit at the November
30 audit. J168 lifts neither SPR-102 nor anything the law requires. SPR-339 (`1786d297`) says the removal adds no
brand-only refusal. Jess's decision TIN-7125 `654c5b08` keeps the `shown-text-unread` refusal on `never_name`
packets. It narrows the scope note TIN-7125 `2201b219` for that refusal and for `shown_text_unread` in `nv subject`.
Elsewhere the removal stands. This table follows both. The removals are video-utils#86, which updates this file, and
xoxd-ai/cade#267. They land together with TIN-7874. The first draft of the re-land closed unmerged.

| Part | After the removal |
| --- | --- |
| Name check on `visible_text` rows | It stays with its `private-term` refusal, so a name in a row still refuses wherever the guard step runs. The registration hook stops forcing that step on a DAG, and a DAG without the step reads no row |
| The open limit | Its effect returns on a DAG without the step, this time by ruling. The open row above says so, and the root keeps it until the audit decides |
| `shown-text-unread` in the hand-off worker | It stays on a `never_name` packet, and BIZ-17 coverage stays with it. The hand-off worker drops it on any other packet |
| `shown_text_unread` in `nv subject` | It stays on a `never_name` packet. `nv subject` refuses it when the guarded intake's marker says `never_name`, or predates that flag, and any shown text is unreadable. The marker's `never_name` must match `private_terms.never_name` in the `intake.json` beside the records, or the read refuses `private_terms_stale`. On any other packet `nv subject` stops refusing it. It keeps the rows that read and prints the unread kinds as `shown_unread`, so a subject can leave shown text out. The Cade client-video worker reads `never_name` from the packet record and refuses `shown_text_unread` from a non-empty `shown_unread` on a `never_name` packet, and `subject-invalid` when that subject has no `shown_unread` key (TIN-7874). The hand-off refusal above also applies on a `never_name` packet |
| The `visible_text` gate | #86 does not change `deliver.py`. On a guarded intake an unread or opaque asset still waits at the operator. Without one the gate reads `not_applicable`, so nothing waits there |
| The intake's `nv` denylist | `ip_private` no longer needs a denylist, and number and geometry entries and the `script` class stop matching. `never_name` keeps its denylist, its name entry and its match |
| Limits that stay | The first row has no change. In the second, a letter outside ASCII stops refusing, so a translation passes in any letters |
