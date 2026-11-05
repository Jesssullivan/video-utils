# TIN-7788 intake and frame gates

Date: November 5, 2026. Base: `fix/tin-7994-lift-confidential` at `388c06b5`. Authority: Jess's rulings on TIN-7125
(`3672cb05`, one general row reusing the render stage), the sprint plan on TIN-7125 (`4f75ce59`) and stage 10 of the
private requirements note, under R-HOOK-CONVERGENCE-20261004 (R-N13). This adds no spec, Dhall type or repository. It
extends `docs/spec/NARRATED_VIDEO.md`, `docs/spec/RENDER_STAGE.md` and the existing `Avatar` record.

## Why

Earlier review renders passed `deliver_check` with frame findings open (TIN-7788 `eecee03c`, `845695a5`). The checks
that found them ran by hand, on composed frames and slide layers (`fcc8ded6`). An invalid claim stood down two GPU
windows because a seat ran the claims gate by hand first (`d00e7549`). The row and the render stage held no step for
either.

## What changed

| Stream | Change | Evidence |
| --- | --- | --- |
| Pre-spend phases | `claims_gate` and `preflight` join the render stage's plan, before `voice_plan` and any window | `test_no_gpu_phase_comes_before_the_gates` |
| Preflight | `render-stage preflight` writes `JOB/intake/preflight.json` and refuses the first finding. `narrate video preflight` is the same reading for a seat's job and writes nothing | `narrate/tests/test_narrated_video_frames.py` |
| Result binding | `render-stage result` refuses `intake_missing`, `preflight_stale` or `preflight_failed`. The report binds `intake_sha256`, and a preflight that crashes leaves no earlier pass | `test_a_result_needs_a_passed_preflight_of_this_job`, `test_a_preflight_that_crashes_leaves_no_earlier_pass` |
| Final artifact | `deliver_check` adds machine gates `avatar_box` and `slide_match`, so `nv cut` and `machine_passed` cover frames. `deliver_check` moves to impl 3 | `test_a_planted_fault_fails_the_cut_and_the_cut_never_reaches_the_operator` |
| Exemption | A bundle asset's `avatar_box: exempt` reaches the job as `avatar.boxExempt`. A job with no slides lists segments and covers its `program` page. A job written before the field stays valid and keeps its digest | `test_a_job_written_before_box_exempt_stays_valid_with_its_digest`, `test_an_exempt_mp4_only_bundle_passes_intake_and_covers_its_program_page` |
| Operator view | `nv cut` and the render stage result print `frame_review`, the page ids no frame gate read | `test_unread_pages_reach_the_cut_and_the_deliver_check_report` |

## Planted faults

Each one is synthetic: a white field with a drawn block, a changed claim or a swapped digest.

| Fault | Refuses at | Code |
| --- | --- | --- |
| A spoken number no claim backs | `intake`, and `claims_gate` on the same read | `number_unclaimed` |
| Content in the avatar box on a slide | `preflight` | `avatar_box_occupied` |
| Content in the box on a base video after the first second | `preflight`, sampled across the page | `avatar_box_occupied` |
| A card that reaches the box | `preflight` | `card_in_avatar_box` |
| An `intake.json` row edited to disagree with the job | `preflight` | `slide_page_mismatch` |
| A slide changed in the store, with a fresh index, through `cli.main` | `preflight`, with the report written | `slide_digest_mismatch` |
| A Full slide that leaves a strip | `preflight` | `slide_letterbox` |
| A cut that shows another slide | `deliver_check` | `slide_not_shown` |
| Content outside the avatar's alpha in a composed frame | `deliver_check` | `avatar_box_occupied` |

The same planted slide refuses a `gpu_window` request at `preflight` too, before any window would start.

## Producer boundary

These gates compare pixels with pixels. The rule that a slide draws the numbers its beat speaks stays with the
producer, in its shown record and demo check (TIN-7788 `8c47686a`). This repository reads neither. The producer's box
check on its PNGs also stays, and `preflight` adds the base video, which the producer's standard-library check cannot
decode (`7b7b4cfe`).

## Limits

| Item | State |
| --- | --- |
| Tests | Synthetic only. No real render, bundle or slide was read. The tolerances carry over from the hand check. The 0.5% slide limit rests on one dense test pattern, which measured 0.206% at the Contingency profile. `deliver_check.json` records each page's share under `slide_match.frames_read`, so the first real job can check the limit |
| Regression control | The hand check's real negative control was not repeated here |
| A page with any unflat sample | Listed as `unchecked`, and it does not fail the gate. `frame_review` puts the page id in `nv cut` and the result, so Jess's GO is the review of that page. No gate read it. A real base with a fade will land here, so the first real job should check how many pages stay unchecked |
| `slide_page_mismatch` | One `convert` wrote the job and the rows, so it catches a later edit of `intake.json`. It does not catch a wrong citation in a bundle |
| Preflight order | `result` proves a preflight passed for this job and intake, and it does not prove the preflight ran before voice work. The mapping below must carry that order |
| Dead air | Not added. It needs a planned-beat rule, and stage 13 owns the deck gates |
| Slide with alpha | Compared without its alpha, so it may fail `slide_match` |
| `voice_qa` and fit | Still after spend. The pre-window fit check belongs to stage 11 |

## Merge order

`git merge-tree` against `feat/tin-7788-rerun-mixed-takes` reports content conflicts in 5 files:
`.agents/skills/narrated-video-verify/SKILL.md`, `docs/spec/RENDER_STAGE.md`, `just/narrated-video.just`,
`narrate/video/cli.py` and `narrate/video/render_stage.py`. Trial merges with `feat/tin-7788-render-graph-repair` and
the current base report none.

Land the rerun lane first and merge it here, because this branch holds the smaller side of each hunk. Most hunks keep
both sides. Three need a decision at merge:

| Hunk | Rule |
| --- | --- |
| `phases` | `claims_gate`, `intake` and `preflight` come before `voice_takes`, so a rerun's takes check follows the gates |
| `result` | `preflight_binding` runs before the rerun record, so a refused result records no render |
| A rerun's new intake | It writes a new `intake.json`, so the old preflight reads `preflight_stale`. The rerun's plan must run `preflight` again |

## Next

| stream | owner | repo/branch | state/evidence | next |
| --- | --- | --- | --- | --- |
| gates | narrate | video-utils `feat/tin-7788-intake-gates` | committed locally, not pushed | draft PR on `fix/tin-7994-lift-confidential` |
| exemption field | the producer | producer template | unknown whether its bundle check accepts `avatar_box` | the producer marks renders that reach the box |
| row tasks | CADE-1 | cade, cade-infra | not started. The gate list and the row's task list still hold four gates | map the two new phases and six gates, refuse voice work without a passed preflight, and show `frame_review` in the GO request |
| merge order | narrate | video-utils `feat/tin-7788-rerun-mixed-takes` | 5 files conflict, see "Merge order" | land the rerun lane first, then merge it here |
| existing cuts | narrate | private job roots | `deliver_check` reruns on the next run, and a page with no declared exemption can now fail | re-intake with the producer's exemption |
