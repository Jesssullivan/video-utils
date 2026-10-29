# Narrated video: demo bundle intake and the claims gate (2026-10-29)

Authority: Linear TIN-7735 (parent TIN-7084), SPR-84 (no new schema) and
repository AGENTS.md. Receipt per R-HOOK-CONVERGENCE-20261004 (R-N11, R-N12,
R-N13).

`demo bundle intake | narrate seat | video-utils feat/tin-7735-demo-bundle-intake (from main eb8f2779) | intake, claims gate, recipes, drafts, skill, synthetic tests; checks below | root review and merge; L7 admits the two drafted tools`

## What changed

| Area | Files | Change |
| --- | --- | --- |
| Bundle | `narrate/video/bundle.py` | strict reader of `manifest.json`, `script.md` and `claims.json`; every asset re-hashed; conversion to one `NarratedVideo` job and one confidential Markdown narrate job per beat; admit before any write; `intake.json` |
| Claims gate | `narrate/video/claims.py` | extraction of digits and spelled-out English numbers, decimals, ordinals, percentages and units; per-segment matching against cited, receipted claims; fail-closed ambiguity |
| CLI | `narrate/video/cli.py` | `intake`, `claims`, and `fixture --bundle` |
| Fixture | `narrate/video/fixture.py` | the synthetic `demo-fixture` bundle: the generated slide pictures, a 1x1 GIF and fixture receipts |
| Recipes | `just/narrated-video.just` | `narrated-video-claims`, `narrated-video-intake`, `nv-intake-fixture`; `nv-test` runs the intake tests |
| Hooks and skills | `program/tool-drafts/narrated_video.json`, `.agents/skills/narrated-video-intake/SKILL.md`, `.agents/skills/narrated-video/SKILL.md` | drafts `narrated_video_intake` and `narrated_video_claims` (no number proposed, not admitted) and their skill |
| Spec | `docs/spec/NARRATED_VIDEO.md` | "Demo bundle intake": format, refusals, conversion, output layout, claims gate; two unknowns |
| Tests | `narrate/tests/test_narrated_video_intake.py`, `narrate/tests/stdlib_smoke.py` | intake and gate tests; the two modules in the smoke list |

No Dhall type, example or `check.py` rule changed. The intake writes the
`NarratedVideo` and narrate `Job` shapes that `job.check_shape`, admit and the
executor already read, and one test runs a converted job through
`deliver_check` on the fake engine.

## Evidence

Every check ran in `systemd-run --user --scope -p MemoryMax=6G
-p MemorySwapMax=0 nice -n 19 env -i PATH HOME TMPDIR`, inside
`nix develop .#condense` (or the default shell for Dhall).

| Check | Result |
| --- | --- |
| `just narrate-test` | 1153 passed, 1 skipped |
| `just nv-test` | 348 passed |
| intake tests (`test_narrated_video_intake.py`) | 109 passed (all new) |
| `narrate/tests/stdlib_smoke.py` | 7 tests OK |
| `just narrate-lint` (ruff check, ruff format, shellcheck) | clean |
| `just narrate-dhall-check` | errors 0; self-test 79 mutations refused |
| `tests/test_public_tree.py` | 4 passed, 1 skipped |
| `just nv-intake-fixture` | claims passed for both segments; intake and init admitted |

The end-to-end test measured, on the fixture sine voice: narrations fitted to
8.0 s and 8.5 s, placed at 0 s and 8 s; `internal_review_allowed` true;
listening `pending_operator`. These are fixture numbers, not a listening result.

## Unknowns

- No real bundle has run. The producing lane's bundles stay in its private
  repository; their first intake runs there.
- The gate reads English number words and the unit table in the spec. It checks
  that a receipt is named, not what it says.
- A bundle's MP4 plays from program second 0 under every beat.

## Review fixes (2026-10-29)

`review fixes | narrate seat | video-utils feat/tin-7735-demo-bundle-intake (PR #68, from b2bc2b0) | five findings applied as new signed commits; checks below | root review`

| Finding | Change |
| --- | --- |
| high: spoken numbers past the gate | `claims.py`: a scale word with no count is `scale_without_count`; plural scale words, "-fold" words, "nil", "nought", "naught", decade words, "a third" and "an eighth" are vague; any non-ASCII numeral makes a digit token; Roman numerals of I, V and X are `roman_numeral`; U+2010, U+2011 and the soft hyphen join words and other dashes between number words are `dash_between_numbers`; "five's" reads as 5; "90s" is `decade_or_seconds` |
| medium: writes before `put()` refused | `bundle.py`: every store target is checked first, then staged; the output tree is built in a temporary sibling and renamed; a refusal removes staged files, new store files and new directories |
| medium: asset re-read unchecked | each asset is copied through descriptors opened with `O_NOFOLLOW` per component and re-hashed against its manifest sha256 (`asset_digest_mismatch`, `asset_missing`) |
| low: pronunciation tables | `intake` says each paragraph through the template's `Normaliser` (and the narration register's upstream table from `NARRATE_LEXICAL_DIR`) and refuses `pronunciation_adds_number` |
| low: unknown scales and units | a single letter, a scale abbreviation, a vowel-less lower-case unit, a binary prefix, a mixed-case unit or a listed capital unit after a number is `unknown_scale_or_unit`; symbols match in exact case and after spelled numbers; "m/s" reads as `m/s`, a "/" to a non-unit is `unit_not_read` |
| nit: claims tool draft | read-only timeout and closing sentences; intake draft states the atomic write |

Spec "Demo bundle intake" and its unknowns, the intake skill and both drafts
follow the code. Each finding has a synthetic regression test in
`narrate/tests/test_narrated_video_intake.py`.
