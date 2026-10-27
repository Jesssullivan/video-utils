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

## Review fixes for PR #58 (2026-10-27)

Authority: the PR #58 review findings relayed by the narrated-video workflow,
under KP-13 and NV-1 to NV-5. Receipt per R-HOOK-CONVERGENCE-20261004 (R-N13).

| Finding | Fix | Test |
| --- | --- | --- |
| `run_avatar` recorded every refusal, so a timeout left the avatar refused for its key | `KitpipRefused.verdict`. kitpip's own refusal line and the wrapper's checks on a finished overlay are verdicts and are recorded. `kitpip_timeout`, `kitpip_error`, `kitpip_missing` and a pin mismatch at spawn are failures: the partial is removed, nothing is recorded and the node stays stale. `JobStore.clear_refusal` drops a verdict for `run --force` (L4) | `test_a_wrapper_failure_is_not_recorded_and_the_avatar_stays_runnable` (3 cases), `test_a_binary_that_fails_its_pin_at_spawn_is_not_recorded` |
| `knobs_for('avatar')` keyed the default rig's revision for any rig | the pin's revision only for the default rig. Another rig with no revision keys none, and `measurements.rig` records what kitpip reports. `run_avatar(rig_sha256=...)` refuses `kitpip_pin_mismatch` when the overlay's revision differs | `test_the_avatar_keys_the_default_rig_revision_only_for_the_default_rig` (5 cases), the rig row below |
| the label chain did not compare `voice_ids` | the overlay must carry the narration's `voice_ids` too | `test_an_overlay_that_alters_a_label_or_the_rig_revision_refuses_and_is_recorded` (5 cases: voice id dropped or altered, consent id dropped, synthetic false, rig revision) |
| a damaged `current.json` or `graph.json` raised a traceback | both refuse `store_invalid` in the stderr shape | `test_a_damaged_current_or_graph_file_refuses_store_invalid` (5 cases) |
| `check_shape` checked only the top level | `job.SHAPE` walks every NarratedVideo field, so `init --from` refuses `job_invalid` before writing | 15 new `test_a_misshapen_job_refuses` cases, `test_cli_init_from_a_misshapen_record_refuses_and_writes_nothing` |
| `init` leaves the avatar off without a recorded reason | recorded as "Avatar opt-in until L6" beside the Defaults table in `docs/spec/NARRATED_VIDEO.md`, citing NV-4. The skill and `just nv-init` comment point to it | none, a documented decision |

Negative control: the new tests run against the previous `narrate/video/`
(stashed) gave 32 failed and 69 passed. With the fixes: 101 passed.

Gates after the fixes, each inside `nix develop .#condense` under
`systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 nice -n 19`:

| Check | Result |
| --- | --- |
| `narrate/tests/test_narrated_video_graph.py` | 101 passed |
| `just narrate-test` | 858 passed, 1 skipped |
| `just narrate-lint` | ruff check, ruff format and shellcheck clean |
| `just narrate-dhall-check` | exit 0, 66 self-test mutations |
| `narrate/tests/stdlib_smoke.py` (repo root on `PYTHONPATH`) | 7 tests OK |
| `tests.test_public_tree`, `tests.test_timeline_contract` | 79 tests OK, 1 skipped |
| `just check` (`just test`) | 2206 tests: 2 failed, 6 errors, 188 skipped. All 8 are marked-video, marked-compact, arrangement or tool-contract renders raising `No bounded supported installed font found`, as in the first round. None reads a file this branch changes |
| `scripts/doctor.py --require-media` | exit 0 |
