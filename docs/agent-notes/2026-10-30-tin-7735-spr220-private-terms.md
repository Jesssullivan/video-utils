# Narrated video: the private-terms guard in the claims gate (2026-10-30)

Authority: Linear TIN-7735 (parent TIN-7084), SPR-220 (an explicit ip_private
guard), the standing authorization SPR-214 (TIN-7125) for narrate-dispatched
lanes and repository AGENTS.md. Receipt per R-HOOK-CONVERGENCE-20261004 (R-N11,
R-N12, R-N13).

`private-terms guard | narrate-dispatched lane | video-utils feat/tin-7735-spr220-private-terms (from main c1a6373c) | guard, CLI flag, recipes, drafts, skill, spec, synthetic tests; checks below | root review and merge`

## What changed

| Area | Files | Change |
| --- | --- | --- |
| Guard | `narrate/video/private_terms.py` | the manifest `privacy` declaration, the `nv_denylist` reader and the matcher. It fails closed and its reports carry positions, entry ids and classes only |
| Bundle | `narrate/video/bundle.py` | `claims` and `intake` run the guard before the number gate: record texts first, then voiced, claim, label and, at intake, spoken texts |
| CLI | `narrate/video/cli.py` | `--denylist FILE` or `NARRATED_VIDEO_DENYLIST` on `claims` and `intake` |
| Recipes | `just/narrated-video.just` | `narrated-video-claims` passes arguments; `nv-test` runs the guard tests |
| Hooks and skill | `program/tool-drafts/narrated_video.json`, `.agents/skills/narrated-video-intake/SKILL.md` | a `denylist` input on both drafted tools, the new codes and a limitation |
| Spec | `docs/spec/NARRATED_VIDEO.md` | "Private terms" under "Demo bundle intake", four refusal codes and the command rows |
| Tests | `narrate/tests/test_narrated_video_private_terms.py`, `narrate/tests/stdlib_smoke.py` | 73 synthetic cases; the module joins the smoke list |

The denylist schema is new and lives outside git. It holds a random salt, so the digest that records carry cannot confirm a guessed short list. The bundle manifest gains
one optional block. No Dhall type or `check.py` rule changed.

## Evidence

Local, non-qualifying: load1 was above 24, so the full `just narrate-test` ran
only in CI. Each check ran under `nice -n 10` inside `nix develop .#condense`.

| Check | Result |
| --- | --- |
| guard, intake and units tests | 587 passed |
| `test_narrated_video_private_terms.py` | 73 passed |
| `just narrate-lint` ruff check and ruff format | clean |
| `test_s5_tool_admission`, `test_s4b_tool_admission` | 24 tests OK |
| `just capabilities-check` | exit 0 |
| `python3 -m unittest narrate.tests.stdlib_smoke` | 7 tests OK |

## Unknowns

- A paraphrase, a translation or a number the claims gate does not read passes
  the guard. The producer still reviews the script.
- The guard runs on bundle intake and the claims gate. A job written another way
  never meets it. Cade's BS-21 step (TIN-7788) is the publish-side check.

## Review round 2 (2026-10-30)

Authority: SPR-214 (TIN-7125 comment 0cbbe60a) and the review verdict FIX on
#74 head 4eb3a2f6. Receipt per R-HOOK-CONVERGENCE-20261004 (R-N13).

| Finding | Change |
| --- | --- |
| F3 respellings | literals match squeezed (letters and digits only, anywhere); NFKD with marks stripped; capital and small confusables mapped; a Latin and Cyrillic word refuses as class `script`; regexes also run on the squeezed fold |
| F7 self opt-in | `--denylist-sha256` or `NARRATED_VIDEO_DENYLIST_SHA256` pins the list outside the bundle and refuses `privacy_undeclared`; a list inside the bundle or a git work tree refuses `denylist_misplaced` |
| F8 later edits | a guarded intake writes `records/private-terms.json`; every records load refuses `private_terms_stale` when a narrate job or its pronunciation table changed |
| F9 early refusals | the guard is built before any bundle check, and any other refusal whose detail says a term is withheld; the duplicate-key detail no longer names the key |
| F10 ids | number entries run against ids too; a refusal detail names the entry by index |
| F11 numbers | NFKC and ASCII digits before reading; digit runs read whole, as a decimal and by group; vulgar fractions; English spellings; units no longer narrow |
| F12 parsers | a shared regex subset, a salt of at least 8 distinct hex digits, and `nv-denylist-conformance.json`, which cade keeps byte-identical |
| F13 unread | the spec lists pixels, frames, burned-in text and container metadata; intake states add `producer_review: pending_operator` |

### F4 proposal, not applied (Jess's act, SPR-138)

1. Add `.github/CODEOWNERS` owning `/narrate/video/private_terms.py`,
   `/narrate/video/bundle.py`, `/narrate/video/claims.py`,
   `/narrate/video/cli.py`, `/narrate/video/job.py`, `/narrate/normalise.py`,
   `/narrate/tests/test_narrated_video_private_terms.py`,
   `/narrate/tests/fixtures/narrated-video/nv-denylist-conformance.json`,
   `/just/narrated-video.just`, `/docs/spec/NARRATED_VIDEO.md`, `/.github/`
   and `/flake.nix` with `@Jesssullivan`.
2. Add to ruleset 25222169 on `main`: `pull_request`
   `{required_approving_review_count: 0, require_code_owner_review: true,
   dismiss_stale_reviews_on_push: true, require_last_push_approval: false}`;
   `required_status_checks` `{strict_required_status_checks_policy: true,
   checks: [narrate, offline, bazel]}`; no bypass actors.

### Round 2 evidence

Local, non-qualifying, under `nice -n 10` in `nix develop .#condense`, load1
about 13.

| Check | Result |
| --- | --- |
| private-terms, intake, units, graph, types, simple, adopt and stdlib smoke tests | 877 passed, 47 subtests |
| `ruff check .` and `ruff format --check .` in `narrate/` | clean |

### Unknowns after round 2

- Hyphen-joined digits ("12-5") are not read as a decimal, because dates would
  then match every short private number.
- Leetspeak and abbreviations need their own entries.
- Deleting `records/private-terms.json` removes the F8 check.
