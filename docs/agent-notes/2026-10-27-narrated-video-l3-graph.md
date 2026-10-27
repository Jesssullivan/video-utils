# Narrated video L3: graph core (2026-10-27)

Authority: operator direction KP-13 and rulings NV-1 to NV-5 (Linear TIN-7476
comments `94248deb`, `1c16fbda` and `9db389dc`). NV-4 starts this lane after L2.
Receipt per R-HOOK-CONVERGENCE-20261004 (R-N13).

`narrated-video L3 | narrate seat | video-utils feat/narrated-video-l3-graph (stacked on PR #56) | graph core, CLI, recipes, stub stage; gates below | root review and merge after #56, then L4 simple path`

A first attempt stopped at a rate limit with the work uncommitted. This round
reviewed that work, kept it, fixed 5 defects and added the tests, recipes,
spec sections, tool draft and skill.

## What changed

| Area | Files | Change |
| --- | --- | --- |
| Graph | `narrate/video/graph.py`, `program/dags/narrated-video.json` | the 13 stages, their edges, knob owners and planner. A test keeps the two tables equal |
| Keys | `narrate/video/keys.py` | canonical JSON, stage keys and the manifest content digest (commit, run dir and time left out) |
| Store | `narrate/video/store.py` | `artifacts/narrated/<job_id>/`, `<key16>.partial/` then rename, `current.json`, `history/`, re-hash freshness |
| Gate | `narrate/video/admit.py` | the Plan point: consent, persona, bed, tighten, bounds, kitpip pin and `Edition.check` through the `check.py` port |
| Jobs | `narrate/video/job.py` | `NarratedVideo.defaults`, `init_job`, record loading and the shape check |
| kitpip | `narrate/video/kitpip.py`, `narrate/tests/fixtures/narrated-video/{kitpip_stub.py,kitpip-externals.json}` | pin resolution, check before every spawn, refusal relay, the avatar stage. The stub writes ProRes 4444 with transparent corners and no kitpip art |
| CLI | `narrate/video/cli.py`, `narrate/__main__.py` | `python -m narrate video {init,plan,status,explain,verify}` |
| Recipes | `just/narrated-video.just`, `justfile` | `nv-init`, `nv-plan`, `nv-status`, `nv-explain`, `nv-verify`, `nv-fixture`, `nv-test` |
| Hook and skill | `program/tool-drafts/narrated_video.json`, `.agents/skills/narrated-video/SKILL.md` | `narrated_video_plan` draft (proposed 62), not admitted. L7 admits it |
| Spec | `docs/spec/NARRATED_VIDEO.md` | "Stage keys and the store", "kitpip pin and the stub" and "Commands" |
| Tests | `narrate/tests/test_narrated_video_graph.py`, `narrate/tests/stdlib_smoke.py`, `tests/test_public_tree.py` | 70 graph tests. The smoke imports `narrate/video`. The public tree refuses media and a kitpip repository URL |
| Bazel | `narrate/BUILD.bazel` | `video/*.py` joins the `narrate` library |

Review fixes to the first attempt:

| Defect | Fix |
| --- | --- |
| `load_pin` called `.get` on a non-object record | refuses `externals_invalid` first |
| `store.manifest` raised on a damaged manifest during `explain` | returns none |
| `deliver_check` keyed on `delivery.handoff` | handoff is no longer its knob, so turning handoff on reruns `handoff` only |
| `bed_content_id_unchecked` also fired on a missing PDF | it reads the Content ID result alone |
| `init --from` silently ignored the defaults flags | refuses `usage` |

## Evidence

All runs used `nix develop .#condense` inside `systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 nice -n 19`.

| Check | Result |
| --- | --- |
| `narrate/tests/test_narrated_video_graph.py` | 70 passed. The stub avatar tests render a fake-engine narrate run and read the overlay's corner and centre alpha |
| Negative controls (scratch copy) | avatar `width` moved into the avatar knobs: the overlay-width row fails. Freshness without re-hashing: 3 freshness and CLI tests fail |
| `just narrate-test` | 827 passed, 1 skipped |
| `just narrate-lint` | ruff and shellcheck clean |
| `just narrate-dhall-check` | exit 0 |
| `narrate/tests/stdlib_smoke.py` | 7 tests OK, including the `narrate/video` imports and the card plan |
| `tests.test_public_tree`, `tests.test_timeline_contract` | 79 tests OK, 1 skipped (no private terms file) |
| `just check` (`just test`) | 2207 tests: 9 failed or errored, 175 skipped. 8 are the marked-video, marked-compact and arrangement renders raising `No bounded supported installed font found`, as in the L2 receipt. 1 is `test_media` AAC overshoot (`AAC true peak -1.39 dBTP exceeds target -1.50`), which fails the same way at L2 head `bb6a6c98`. No failing test reads a file this branch changes |
| `scripts/doctor.py --require-media` (the rest of `just check`) | exit 0 |
| `just nv-fixture` | admit Admitted, 9 stale, 3 not selected |

## Unknowns and next

- `run`, `stage`, `pin-check` and the stages other than avatar are L4 to L6.
  The voice stage must record which narrate run the avatar stage reads.
- The real kitpip pin is a private record (NV-1). Its digests arrive with the
  kitpip release (L5).
- Root records the narrated-video issue ids in `program/linear.json` when it
  confirms the W8 lane name.
