# Typed findings and machine-started rounds (November 7, 2026)

Linear TIN-7788, ruling TIN-7125 `0690fe88`, plan items 1.1 and 1.2 of the loop core. Video-utils half only. Receipt
cites R-HOOK-CONVERGENCE-20261004 (R-N13). Nothing ran on a GPU, an engine or a Hatchet row. Fixtures are synthetic.

`findings and rounds | narrate lane | video-utils feat/tin-7788-typed-findings-machine-round | local tests below | root integrates`

## What changed

| File | Change |
| --- | --- |
| `narrate/video/findings.py` | the record, the code table, `report` and `check` |
| `narrate/video/frames.py`, `deliver.py`, `speech.py`, `claims.py`, `bundle.py` | each gives every code and page as typed rows |
| `narrate/video/render_stage.py`, `cli.py` | `job_findings`, and the commands `findings`, `campaign-bind`, `round` and `fix --extend` |
| `narrate/video/graph.py` | `reach`: the stages a fix may run from where it enters |
| `narrate/video/rerun.py` | `bind_campaign`, `machine_round`, the `parked` record and the extended FIX row |

## Decisions in this draft

- A gate still stops on its first code with its old exit code. Refused intake and claims now also print a `findings`
  key on stdout, which they did not print before when the refusal carried no report.
- Stage bytes stay. Readers parse `deliver_check.json` and `lexical.json`, because a new byte in `lexical.json` moves
  every voice key.
- Only `campaign-bind` opens a round with no decision, and a client edition refuses it. The binding checks the id's form
  only. That a signed campaign record holds the id stays the caller's check, as `rerun.json` carries no signature.
- `check` refuses a code, gate or stage that is not one short token, because a round's ledger row holds the codes as
  written.
- A slide finding only a composed cut can show needs `--video-sha256`. Without it the round would bind no cut, so an
  unchanged cut could answer it.
- A machine round never passes the cap. Past it the root parks, exits 0 and asks nobody. `fix --extend` stays a person's
  decision, one round each.

## Open for the loop controller

The same findings on the same cut or job are a no-op with `recorded: false`, and that spends no round. A fix that changes
nothing therefore never reaches `parked` on this side. The controller in item 1.4 has to stop on `recorded: false`.

`round_out_of_reach` refuses when `result` records the render, so a wrong fix has already spent its render. It stops the
record, not the spend.

## Adversarial review

Review of `8154cc3` against plan items 1.1 and 1.2. Each row was a fault the branch held before these commits.

| Fault | Fix | Test |
| --- | --- | --- |
| A round on a cut with no render row skipped the reach check, so a re-voice on a slide round recorded as its answer. Cade's row never calls `result`, so a root can reach this on its first cut | the round row holds `seq`, and `check_reach` reads what committed after it | `test_a_re_voice_on_a_slide_round_refuses_on_a_cut_with_no_render_row` |
| A second round refused a compose fix for a re-voice round 1 had asked for | the same counter | `test_what_ran_before_a_round_is_not_that_rounds_to_answer` |
| A failed gate no limit explains, such as a NaN loudness, gave no row, so `ok` read true on a failed cut | `gate_failed`, which no stage bounds | `test_every_failed_gate_gives_a_row` |
| A deliver_check or preflight of an older `job.json` gave rows and a cut for the current job | `job_findings` reads the current render and says `current`, `stale` or `missing` | `test_a_deliver_check_of_an_older_job_gives_no_row_and_no_cut` |
| A token could hold a path, and a key any text | a token holds no slash except a ratio, and `plain` reads keys | `test_a_record_holds_no_text`, `test_a_key_of_a_record_holds_no_text` |
| `round` took a report of another job or job.json, and a cut other than the one it read | `findings_stale`, `video_mismatch` | `test_a_round_refuses_with_nothing_recorded` |
| An avatar frame row could start a round with no cut | `findings.reads_cut` | same parametrized test |
| `test_reading_findings_moves_no_stage_key` only pinned two constants | the real root test compares every file under the job root before and after | `test_the_findings_of_a_real_root_are_typed_and_hold_a_real_lexical_finding` |

Left as they are, each failing closed or owned by a later item:

- `ok` speaks for the rows only. A job with no current `deliver_check` reads `ok: true`, and a machine must read `deliver_check` beside it. Cade's item 1.4 reads neither as a pass.
- A page no frame gate read stays `unchecked` and gives no row, as `frame_review` shows. Campaign jobs have nobody reading that view, so item 2.6 owns it.
- `job_findings` lists every refusal in `current.json`, including one whose key has moved. An old refusal can only add a row, widen a reach or spend a round.
- A round that named no cut on a root with no render still has nothing to compare.
- A stage refusal's row enters at its own stage, which can be narrower than its fix. That render refuses `round_out_of_reach`, and the root reaches the cap and parks.

## Checks

Local and non-qualifying, each under the repo's capped test wrapper in the `condense` dev shell, `cd narrate` first:

| Command | Result |
| --- | --- |
| `python3 -m pytest -q tests/test_narrated_video_findings.py tests/test_narrated_video_rerun.py tests/test_narrated_video_accept.py tests/test_narrated_video_claims_units.py` | 681 passed |
| `python3 -m pytest -q tests/test_narrated_video_intake.py tests/test_narrated_video_private_terms.py tests/test_narrated_video_visible_text.py tests/test_narrated_video_frames.py tests/test_narrated_video_render_stage.py tests/test_narrated_video_graph.py tests/test_narrated_video_subject.py` | 924 passed |
| `ruff check` on the changed Python, `ruff format --check` on the 4 files last edited | clean |
| After the review: `python3 -m pytest -q tests/test_narrated_video_findings.py tests/test_narrated_video_rerun.py` | 250 passed |
| After the review: `python3 -m pytest -q tests/test_narrated_video_accept.py tests/test_narrated_video_render_stage.py tests/test_narrated_video_graph.py tests/test_narrated_video_frames.py tests/test_narrated_video_subject.py tests/test_narrated_video_claims_units.py` | 774 passed |
| After the review: `ruff check` on `narrate/video` and both test files, `ruff format --check` on the 6 files edited | clean |

Not run: the full narrate suite, `just narrate-lint`, CI, Bazel, a real engine, a real render or listening. No mutation
test ran. These paths hold no signal call.
