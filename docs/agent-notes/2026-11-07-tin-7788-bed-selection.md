# Bed selection on campaign jobs

November 7, 2026, narrate seat. Linear TIN-7788, item 2.8 of the DAG plan. Ruling: TIN-7125 `e552e569`, verbatim on music: "Agent should deem if backing music is needed / desirable, and if so Splice credits can and should be agent spendable." Receipt under R-HOOK-CONVERGENCE-20261004.

## What changed

| Part | Change |
| --- | --- |
| `narrate/video/bed_select.py` | New. A judge port, a catalog port, the pick rule, the monthly credit guard, the selection file |
| `narrate/dhall/MusicBed.dhall` | `Acquirer` gains `Agent : { agent : Text }`, the campaign id |
| `narrate/video/admit.py`, `music.py`, `narrate/dhall/check.py` | An agent's record holds only on a non-client job root bound to its campaign, and its id must bind its digests |
| `narrate/video/bundle.py`, `cli.py` | `intake --bed-selection FILE --campaign ID` replaces the fixed `"music": None` when given. `init --campaign` binds the root. `bed-select` is new |
| `docs/research/2026-11-07-splice-terms-campaign-beds.md` | The terms read, with quotes and what would refuse |

## Evidence

| Bar | Test in `narrate/tests/test_narrated_video_bed_select.py` |
| --- | --- |
| A bedless job still passes | `test_a_bedless_selection_gives_a_job_that_passes_through_plan` runs through `deliver_check` on the fake engine. `test_a_job_with_no_selection_is_what_it_was` |
| A selected bed binds by digest | `test_a_selected_bed_binds_each_loop_by_digest_with_its_licence_record`, `test_intake_refuses_a_loop_off_its_digest_and_writes_nothing`, `test_a_bound_campaign_job_runs_the_music_stage_on_the_selected_loops`, `test_a_damaged_loop_refuses_the_music_stage_of_a_bound_job` |
| A guard refuses past the budget | `test_the_guard_refuses_past_the_budget_before_any_download`, `test_the_guard_lets_the_exact_budget_through_and_counts_the_month` |
| NV-3 stands off a campaign | `test_an_agents_bed_is_admitted_only_on_its_campaigns_root`, `test_a_client_edition_refuses_an_agents_bed_even_when_cleared` |

The judge and catalog are fakes and the loops are generated sines. Local and non-qualifying.

## Not done

- No catalog adapter, so no search, download or credit spend through this code.
- No row, no stage in `program/dags/narrated-video.json`, so no task digest moves. Selection runs before a job exists. Wiring it to a task is wave 3.
- `deliver_check` is unchanged. A public cut with a bed stays refused while the record has no licence PDF digest and no clear Content ID result. Neither has an agent route, so item 2.6 or a ruling has to settle it.
- The account question under Splice Terms 2.12 (n) is open for Jess. See the research file.

## For the adapter

The real port must call Splice's MCP server and nothing else, skip previews and stacks, and map a row to `{asset_id, type, bpm, key, preview}`. How a real row marks preview audio is unknown here, because no search ran. The ledger counts by UTC calendar month, and the subscription's month may start on another day.
