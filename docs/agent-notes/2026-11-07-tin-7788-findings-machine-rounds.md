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

## Checks

Local and non-qualifying, each under the repo's capped test wrapper in the `condense` dev shell, `cd narrate` first:

| Command | Result |
| --- | --- |
| `python3 -m pytest -q tests/test_narrated_video_findings.py tests/test_narrated_video_rerun.py tests/test_narrated_video_accept.py tests/test_narrated_video_claims_units.py` | 681 passed |
| `python3 -m pytest -q tests/test_narrated_video_intake.py tests/test_narrated_video_private_terms.py tests/test_narrated_video_visible_text.py tests/test_narrated_video_frames.py tests/test_narrated_video_render_stage.py tests/test_narrated_video_graph.py tests/test_narrated_video_subject.py` | 924 passed |
| `ruff check` on the changed Python, `ruff format --check` on the 4 files last edited | clean |

Not run: the full narrate suite, `just narrate-lint`, CI, Bazel, a real engine, a real render or listening. No mutation
test ran. These paths hold no signal call.
