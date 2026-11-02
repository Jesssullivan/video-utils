# TIN-7788: shown text refix

Date: November 1, 2026. Linear: TIN-7788. Authority: the narrate seat's lane brief with the review findings on
video-utils#84 `be5da311` and xoxd-ai/cade#259 `2878256d`. Receipt cites R-HOOK-CONVERGENCE-20261004 (R-N13).

| stream | owner | repo/branch | state/evidence | next |
| --- | --- | --- | --- | --- |
| shown text reader | narrate lane vu83-84 | Jesssullivan/video-utils `feat/tin-7788-nv-visible-text-subject-20261031`, Jesssullivan/cade `feat/tin-7788-bs21-shown-text-20261031` | **HOLD** draft, video-utils#83 lands first. Local, non-qualifying | root review, CI on both heads |

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
| done | xoxd-ai/cade#250 | merged as `9820a216` (TIN-7788 `84ace0b0`) |
| 1 | video-utils#83 | known limit |
| 2 | video-utils#84 | based on main, with main merged |
| 3 | xoxd-ai/cade#246 | a signed merge of main resolves `docs/BS21_GUARD.md`: keep #246's client-video row and #250's hardware hand-off row |
| 4 | xoxd-ai/cade#259 | at `17d6ee8f` it has main merged, then the doc update below |

This order keeps the known-limit row accurate. It is not a code dependency for cade#246, which calls `nv subject`
through recipes already on main. Until #84 lands, `nv subject` prints no `visible_text` rows, and the row covers that
window (CADE-1's question, TIN-7788 `1e382d98`).

CADE-1 lands cade PRs under SPR-290, and each merge above is the narrate lane's to draft. Whichever of cade#246 and
cade#259 lands second updates `docs/HATCHET_CLIENT_VIDEO.md` lines 23, 37, 44 and 50, as numbered at `749d5d14`. Those
lines still say the subject holds voiced and labelled texts and describe the old `shown_text_unread` cases. The code
needs no change.

## Corrections

Receipt `e6e6330d` covered two branch pushes, #83 and #84, and the receipt rule is one comment per push. Its head text
"CI pending" on #84 is stale: CI read 12 of 12 passing at `be5da311`.

The cade half of this refix waited on cade#250, so parity was not true at this head when it was pushed: cade#259 stayed
at `666e13a4` with 64 source cases and sha256 `15812b8e`, and its reader failed 4 of the 79 cases here. cade#259 reached
`17d6ee8f` on November 2. It holds the fixture with sha256 `a770516f`, the same as this branch.

## Review of `2556e260`

| Finding | Result |
| --- | --- |
| Parity unpublished | true now, see Corrections and Evidence |
| A repointed marker digest passed `nv subject` with no rows | fixed. `intake.json` holds `visible_text.source_sha256`, and `visible_agrees` refuses `private_terms_stale` when a marker's digest differs. A row also needs a string `asset` |
| A lone surrogate crashed a guarded intake | fixed. `json_texts` refuses it as a `TextSourceError` |
| A deep SVG raised `RecursionError` | fixed. `svg_read` loops, so it reads what the TS reader reads |
| Stale strings | fixed in `cli.py`, the just recipe, `bundle.py` and `subject.py` |
| An empty JSON list gives no row | rule kept, and the spec's table of what passes now lists it. Whether to treat it as opaque in both readers stays open for Jess |

Row positions are not compared with the intake's. The review offered that as a second check, but a job's rows differ from
`read` for an empty source, and a forger who can edit both `intake.json` and the marker can edit a position list too.

### Parity left open

The shared fixture stays at `a770516f` here, because a new case needs cade#259 to carry the same bytes. These stay open
for the next pass that moves cade#259.

| Difference | Direction |
| --- | --- |
| A lone surrogate in a JSON source | Python refuses, the TS reader accepts. New here. It fails closed at intake |
| `<style>` with a nested element splitting `@import`: both readers join the text, and the review expects a browser reads direct child text only. An inference, not tested in a browser | both read not opaque |
| An XML declaration with a bad attribute or no version, an unbound prefix on a skipped element, duplicate namespaced attributes, `xmlns:a=""`, a JSON byte-order mark | TS reads, Python refuses |
| Non-ASCII element or attribute names, `schema_version` true | Python reads, TS refuses |
| Attribute `&#10;` and `&#9;`, a dotless i in `image(` | the readers differ |

## What J168 changes

J168 (TIN-7125 `9738d494`) removes the BS-21 and `ip_private` code refusals for go-live, with a revisit at the November
30 audit. SPR-339 (`1786d297`) keeps brand-only refusals out of that change. No removal PR exists yet, so this is the
plan as ruled, and that PR's own text decides.

| Part | After the removal |
| --- | --- |
| `visible_text` rows | `nv subject` still prints them. A name in one no longer refuses at the Cade guard |
| Stored source and digest binding | no change from this branch |
| Shared fixture | still binds what each reader reads. It tests no name-list refusal |
| `shown_text_unread` and cade's `shown-text-unread` | J168 names neither code. The removal PR must say whether they stay |

`docs/spec/DEMO_PACKET.md` on video-utils#83 holds the same plan for the known-limit row.

## Evidence

All runs were local and non-qualifying, in a capped scope, Python 3.14 from `uv`, FFmpeg 8.1.2 headless from the Nix
store. This is not the repository's shell.

| Run | Result |
| --- | --- |
| visible-text, subject and private-terms files | 455 passed |
| `ruff check` and `ruff format --check` on the changed Python files | clean |
| Full `just nv-test` | not run, because load1 stayed above 24, reaching 149. CI runs it |

The review fixes ran on the same local setup, with main `6aa4aca1` merged. Load1 reached 50, so these are targeted runs.

| Run | Result |
| --- | --- |
| visible-text, subject and private-terms files | 461 passed |
| intake, accept, types and render-stage files | 390 passed, 1 skipped |
| `ruff check` and `ruff format --check` on the changed Python files | clean |
| 5 mutation probes: the digest compare, the digest in `intake.json`, the row `asset` check, the surrogate refusal, the `svg_read` order | each failed at least 1 test |
| Fixture sha256 at this branch and at cade#259 `17d6ee8f` | both `a770516f` |
| `tests/bs21-shown-text.test.ts` at cade#259 `17d6ee8f`, no dependencies installed | 7 pass, 0 fail, 79 source and 5 script cases |
| Full `just nv-test` | not run. CI runs it |

No test uses a real slide, name or number. Nothing was merged or marked ready. No host act ran.
