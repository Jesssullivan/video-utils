# TIN-7788: the BS-21 name list reads shown text

Date: October 31, 2026. Linear: TIN-7788. Authority: the narrate seat's visibletext lane brief and CADE-1's note that
intake lives in video-utils. Receipt cites R-HOOK-CONVERGENCE-20261004 (R-N13).

| stream | owner | repo/branch | state/evidence | next |
| --- | --- | --- | --- | --- |
| visible_text in `nv subject` | narrate visibletext lane | Jesssullivan/video-utils `feat/tin-7788-nv-visible-text-subject-20261031`, stacked on #81 | **HOLD** on #81. Local, non-qualifying | root review after #81 |

## What changed

| Part | Change | Files |
| --- | --- | --- |
| Stored source | A guarded intake writes an `nv_visible_text` file to the private store and binds its digest in the records marker as `visible_text.source_sha256` | `narrate/video/bundle.py`, `private_terms.py` |
| Subject | `nv subject` adds one `visible_text` row per shown asset, so the worker hands them to the BS-21 name list | `narrate/video/subject.py` |
| Fail closed | `shown_text_unread` also covers an unread or opaque asset, a marker with no stored source, and a stored source that is gone or malformed | `narrate/video/subject.py` |
| Shared fixture | `nv-shown-text-conformance.json`, byte-identical in xoxd-ai/cade, binds this reader and `src/bs21-shown-text.ts` | `narrate/tests/fixtures/narrated-video/` |

The marker stays at schema 2. A marker with no `source_sha256` still loads, so an earlier intake keeps its other
gates, and only `nv subject` refuses it.

An intake from before this branch that shows an asset now needs a re-intake before a Cade DAG can guard it.
A `partial` intake also refuses at `nv subject`, where before it reached `deliver_check` and waited at the operator.
