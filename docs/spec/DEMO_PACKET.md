# Demo packet known limits

Linear: TIN-7788. Authority: the narrate seat's lane brief, receipt on TIN-7788 comment `e6e6330d`. A demo packet is
the private run record a producer hands to the Cade DAG, so it stays out of this repository. This file holds the limits
a packet carries. The producer's demo README, `docs/demo/<slug>/README.md` in its own private repository, copies the
open rows and cites this file for the limits that stay. That copy is a manual step, and no check reads the README.

## Open limits

| Limit | Effect | What holds today | Closes when |
| --- | --- | --- | --- |
| The BS-21 name list reads no text a slide, plot, clip or deck shows on a path that runs today. The hand-off worker from cade#250 reads each source's raw bytes, and it is off and unregistered. The intake's `nv` denylist reads only a shown PNG or MP4 with a text source, and only when the bundle declares a denylist. Nothing reads a deck's text | A name must be on that denylist for a slide to refuse it. A name only on the BS-21 name list reaches the screen | No machine gate catches a read slide. The `visible_text` gate holds only an unread or opaque asset, and it reads `passed` for a read slide. `producer_review: pending_operator` is a label no code reads. What remains is the operator's own read of each slide, and no gate records that read. A `listening` acceptance records a GO on the cut, with no record of a slide read | video-utils#84, cade#246 and cade#259 have all merged. cade#250 already has, as `9820a216`. This closes the source state only: the guard reads shown text on a running DAG after a worker binding and a declaration exist. The root then removes this row, unless the J168 removal below has landed |

## Limits that stay

| Limit | Why |
| --- | --- |
| Text burned into a frame that the asset's text source does not list, or a text source that differs from its picture, passes every machine check | No check reads pixels or runs OCR. The digest binds the file, not its match to the picture. An asset with no text source is `unread`, so it waits at the operator |
| A paraphrase, or a translation in ASCII letters, passes | No denylist entry spells it. A letter outside ASCII after folding refuses as class `script` |

## J168 removal

J168 (TIN-7125 `9738d494`) removes the BS-21 and `ip_private` code refusals for go-live, with a revisit at the November
30 audit. SPR-339 (`1786d297`) keeps brand-only refusals out of that change. It lifts neither SPR-102 nor anything the
law requires. No removal PR exists yet, so this table is the plan as ruled, and the PR's own text decides each row.

| Part | After the removal |
| --- | --- |
| BS-21 name list | A name in a `visible_text` row no longer refuses at the Cade guard. The rows still reach the guard, and nothing refuses on them |
| The open limit | Its effect returns on a running DAG, this time by ruling. The root rewrites the row to say so, and keeps it until the audit decides |
| `shown_text_unread` and `shown-text-unread` | J168 names neither code. Each stops a subject that leaves shown text out. The removal PR must say whether they stay |
| The intake's `nv` denylist | The removal receipts so far list cade files only. This is an inference from those receipts, and the removal PR must say whether it holds |
| Limits that stay | No change |
