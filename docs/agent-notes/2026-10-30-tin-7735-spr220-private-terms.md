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
| Tests | `narrate/tests/test_narrated_video_private_terms.py`, `narrate/tests/stdlib_smoke.py` | 70 synthetic cases; the module joins the smoke list |

The denylist schema is new and lives outside git. The bundle manifest gains
one optional block. No Dhall type or `check.py` rule changed.

## Evidence

Local, non-qualifying: load1 was above 24, so the full `just narrate-test` ran
only in CI. Each check ran under `nice -n 10` inside `nix develop .#condense`.

| Check | Result |
| --- | --- |
| guard, intake, units and tools-sim tests | 601 passed, 1 skipped |
| `test_narrated_video_private_terms.py` | 70 passed |
| `just narrate-lint` ruff check and ruff format | clean |
| `test_s5_tool_admission`, `test_s4b_tool_admission` | 24 tests OK |
| `just capabilities-check` | exit 0 |
| `python3 -m unittest narrate.tests.stdlib_smoke` | 7 tests OK |

## Unknowns

- A paraphrase, a translation or a number the claims gate does not read passes
  the guard. The producer still reviews the script.
- The guard runs on bundle intake and the claims gate. A job written another way
  never meets it. Cade's BS-21 step (TIN-7788) is the publish-side check.
