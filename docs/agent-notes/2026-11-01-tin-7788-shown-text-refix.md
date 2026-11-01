# TIN-7788: shown text refix

Date: November 1, 2026. Linear: TIN-7788. Authority: the narrate seat's lane brief with the review findings on
video-utils#84 `be5da311` and xoxd-ai/cade#259 `2878256d`. Receipt cites R-HOOK-CONVERGENCE-20261004 (R-N13).

| stream | owner | repo/branch | state/evidence | next |
| --- | --- | --- | --- | --- |
| shown text reader | narrate visibletext lane | Jesssullivan/video-utils `feat/tin-7788-nv-visible-text-subject-20261031`, Jesssullivan/cade `feat/tin-7788-bs21-shown-text-20261031` | **HOLD** on cade#250. Local, non-qualifying | root review, CI on both heads |

## Changed here

| Part | Change | Files |
| --- | --- | --- |
| Style text | `style_text` reads all character data inside a `style` element. It read only the text before the first child, so an import after a comment or a nested element read as not opaque | `narrate/video/visible_text.py` |
| Shared fixture | 15 new source cases, 79 in all, byte-identical in xoxd-ai/cade | `narrate/tests/fixtures/narrated-video/` |
| Spec | one sentence on a `style` element's CSS | `docs/spec/NARRATED_VIDEO.md` |

The review named the TypeScript side of the nested `style` gap. The Python side had its own gap, in the same area and
the other direction, and the new cases cover both: 4 cases fail the old Python reader and 4 fail the old TypeScript
reader. A 6000-case generated differential of `style`, `metadata`, comments and text nesting then gave no difference.

The cade side of this refix holds the linear scans and the time-bounded test. Python's `str.strip` needs no such change.

## Land order

| Land | PR | Note |
| --- | --- | --- |
| done | video-utils#81 | merged to main as `6aa4aca1`, ahead of #83. cade#246 calls its recipes |
| 1 | video-utils#83 | known limit |
| 2 | video-utils#84 | retarget to main first. This branch merges with `6aa4aca1` with no conflict |
| 3 | xoxd-ai/cade#250 | |
| 4 | xoxd-ai/cade#246 | a signed merge of main resolves `docs/BS21_GUARD.md`: keep #246's client-video row and #250's hardware hand-off row |
| 5 | xoxd-ai/cade#259 | a signed merge of main, then the doc update below |

CADE-1 lands cade PRs under SPR-290, and each merge above is the narrate lane's to draft. Whichever of cade#246 and
cade#259 lands second updates `docs/HATCHET_CLIENT_VIDEO.md` lines 23, 37, 44 and 50, as numbered at `749d5d14`. Those
lines still say the subject holds voiced and labelled texts and describe the old `shown_text_unread` cases. The code
needs no change.

## Corrections

Receipt `e6e6330d` covered two branch pushes, #83 and #84, and the receipt rule is one comment per push. Its head text
"CI pending" on #84 is stale: CI read 12 of 12 passing at `be5da311`. This refix makes one push per repository and one
comment for each.

## Evidence

All runs were local and non-qualifying, in a capped scope, Python 3.14 from `uv`, FFmpeg 8.1.2 headless from the Nix
store. This is not the repository's shell.

| Run | Result |
| --- | --- |
| visible-text, subject and private-terms files | 455 passed |
| `ruff check` and `ruff format --check` on the changed Python files | clean |
| Full `just nv-test` | not run, because load1 stayed above 24, reaching 149. CI runs it |

No test uses a real slide, name or number. Nothing was merged or marked ready. No host act ran.
