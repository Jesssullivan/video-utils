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
| A repointed marker digest passed `nv subject` with no rows | fixed when an `intake.json` lies beside the records. That file holds `visible_text.source_sha256`, and `visible_agrees` refuses `private_terms_stale` when a marker's digest differs. A row also needs a string `asset` |
| A lone surrogate crashed a guarded intake | fixed. `json_texts` refuses it as a `TextSourceError` |
| A deep SVG raised `RecursionError` | fixed. `svg_read` loops, so it reads what the TS reader reads |
| Stale strings | fixed in `cli.py`, the just recipe, `bundle.py` and `subject.py` |
| An empty JSON list gives no row | reversed. CADE-1 ruled in seq 1070 that it is opaque in both readers, because that fails closed. A list of only whitespace reads the same, and so does a list of only zero-width text such as U+200B, by CADE-1 seq 1089. A string counts only when it holds a character that is neither whitespace nor in Unicode's Default_Ignorable_Code_Point ranges, in both readers and both kinds of source. A shown asset that truly draws no text cannot say so: on a guarded intake it waits at the operator, and on a `never_name` packet the producer must list a string or drop the asset |

Row positions are not compared with the intake's. The review offered that as a second check, but a forger who can edit
both `intake.json` and the marker can edit a position list too.

### Before a worker binding

The digest check has a condition, and a test pins it. With no `intake.json` beside the records, a marker digest
repointed at a stored document with no rows passes `nv subject` with 0 `visible_text` rows, in any lane. A dangling
symlink at that path refuses. The spec accepts this class because the producer controls OUT. The Cade worker's records
layout is unknown, because no worker binding exists. If `NARRATED_VIDEO_RECORDS` points at a directory with no
`intake.json` beside it, a single marker edit passes. Before that binding, record whether `intake.json` travels with
the records, or make `nv subject` refuse without it.

### Parity left open

The empty-list pass moved the shared fixture in both repositories, for that rule alone. These stay open for the next
pass that moves cade#259.

| Difference | Direction |
| --- | --- |
| A lone surrogate in a JSON source | Python refuses, the TS reader accepts. New here. It fails closed at intake |
| `<style>` with a nested element splitting `@import`: both readers join the text, and the review expects a browser reads direct child text only. An inference, not tested in a browser | both read not opaque |
| An XML declaration with a bad attribute or no version, an unbound prefix on a skipped element, duplicate namespaced attributes, `xmlns:a=""`, a JSON byte-order mark | TS reads, Python refuses |
| Non-ASCII element or attribute names, `schema_version` true | Python reads, TS refuses |
| Attribute `&#10;` and `&#9;`, a dotless i in `image(` | the readers differ |

### Third pass, CADE-1 seq 1089

A list of only zero-width text is opaque in both readers. The shared fixture gains 5 cases, 85 in all, sha256
`bd6ebb2a`, byte-identical in cade#259. Runs were local and non-qualifying, through the heavy-step queue.

| Run | Result |
| --- | --- |
| Fixture cases, Python and TS readers | 85 of 85 agree on each side |
| Code point differential: every code point alone and beside a space, plus shape edges, 2224149 inputs | identical but for 2 inputs: the JSON byte-order mark and the lone surrogate, both listed under Parity left open |
| `ruff check` and `ruff format --check` over `narrate/` | clean |
| visible-text, subject and private-terms files | 477 passed |
| cade `bs21-shown-text`, `hatchet-hardware-handoff`, `guard-closure` and `guard-files` tests | 98 pass, 0 fail |
| 4 TS mutants: zero-width rule, JSON opaque, SVG add, supplementary-plane range | each failed a test |
| 2 Python mutants: zero-width rule, JSON opaque | each failed a test. A third, the supplementary-plane range, did not apply in the bundle. Its rerun result is in the vu#84 body |

## What J168 changes

J168 (TIN-7125 `9738d494`) removes the BS-21 and `ip_private` code refusals for go-live, with a revisit at the November
30 audit. J168 lifts neither SPR-102 nor anything the law requires. SPR-339 (`1786d297`) says the removal adds no
brand-only refusal. This section follows the scope note TIN-7125 `2201b219`, Jess's decision TIN-7125 `654c5b08`, which
narrows that note on `never_name` packets, and the J168 re-land. The re-land has not merged, so its final text decides
each row. CADE-1's seq 1061 gives cade#267 refix findings.

| Part | After the removal |
| --- | --- |
| `visible_text` rows and the name check | `nv subject` still prints a row for each asset it reads. The name check stays with its `private-term` refusal. A name in a row still refuses wherever the guard step runs. The registration hook stops forcing that step on a DAG, so a DAG without it reads no row |
| `shown_text_unread` in `nv subject` | It goes where no `never_name` is known. The re-land keeps it when the records' marker or the `intake.json` beside them says `never_name`, by Jess `654c5b08` and CADE-1 seq 1089. The marker at this head omits the flag, but `intake.json` holds `private_terms.never_name`. With no marker, the Cade worker refuses on the packet record |
| cade's `shown-text-unread` in the hand-off worker | It stays on a `never_name` packet, with BIZ-17 coverage. It goes on any other packet |
| The `nv` denylist | `private_terms.py` and `subject.py` change. `ip_private` no longer needs a denylist, and number and geometry entries and the `script` class stop matching. `never_name` keeps its denylist, its name entry and its match |
| This branch's `shown_text_unread` cases | They reverse. An unread or opaque asset, a marker with no stored source and a stored source that is gone, changed or malformed stop no subject in `nv subject`. The J168 re-land branched before these cases and removes only the no-marker refusal. It conflicts with this branch in 5 files, so it takes a signed merge of this branch and drops them |
| A `partial` intake | Off `never_name` it passes `nv subject`, so a Cade DAG no longer stops there. The J168 re-land does not change `deliver.py`, so the delivery still waits at the operator. On a `never_name` packet `nv subject` and Cade's hand-off both still refuse it |
| A bundle with no text source | It can pass a Cade guard off `never_name`, and the name check then has no text to read for that asset. On a `never_name` packet the hand-off still refuses it |
| Stored source and digest binding | Neither the note nor the J168 re-land changes them. `private_terms_stale` on a repointed digest stays, when an `intake.json` lies beside the records |
| Shared fixture | still binds what each reader reads. It tests no name-list refusal |

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

The second review's fixes on this head did not run locally. The load gate returned 75 at load5 36.60, above its limit
of 24, and nothing ran ungated. These edits have no local run, so CI's hosted `narrate` job is their first run.

| Run | Result |
| --- | --- |
| `test_narrated_video_visible_text.py`, with the new digest test and the whitespace case | not run locally. CI runs it |
| `ruff check` and `ruff format --check` on the changed Python files | not run locally. CI runs them |
| Mutation probes on the new test, full `just nv-test` locally | not run |

No test uses a real slide, name or number. Nothing was merged or marked ready. No host act ran.
