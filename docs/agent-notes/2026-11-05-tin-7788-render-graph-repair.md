# Render graph repair, video-utils half

November 5, 2026. TIN-7788, parent TIN-7125. Receipt cites R-HOOK-CONVERGENCE-20261004 (R-N13) and Jess's ruling
TIN-7125 `3672cb05`: one general row with one pinned graph. Sprint plan: TIN-7125 `4f75ce59`. Nothing here runs a
row, spends, sends or enables anything.

## Decisions

| Item | Decision | Evidence |
| --- | --- | --- |
| One graph | `program/dags/narrated-video.json` stays the source. A `row` block projects it to the 16 Hatchet tasks | `graph.row_tasks`, `test_the_row_task_graph_is_the_published_dag_and_its_digest_is_recorded` |
| Handoff edge | `handoff` takes `deliver_check` as a parent through a new `order` edge. It carries no input | `test_the_order_edge_stays_out_of_the_handoff_key`, `test_a_refused_deliver_check_blocks_handoff` |
| Why an order edge | handoff reads nothing from `deliver_check`, and `deliver_check` keys on the job's digest. A digest edge would tie the layers to a report they never read | `narrate/video/graph.py` `knobs_for`, spec stage table |
| Why any edge | The cade `deliver_check` body refuses failed machine gates, so a child task never starts on a failed cut. Without the edge handoff renders beside it. The spec diagram already drew this order | cade `src/hatchet-client-video.ts` `checkedCut` |
| Operator gates | `handoff` runs while `deliver_check` is `pending_operator`. The row asks Jess after handoff, so waiting on her would hang the run | `test_handoff_runs_after_deliver_check_with_an_operator_gate_open` |
| Dhall | This repository holds no task graph in Dhall and gains none. `selected_by` and `edition_point` tie the DAG to the Dhall job and Edition types | `narrate/dhall/check.py` `check_stage_graph`, 8 new self-test mutations |
| Tool names | `kitpip_overlay` and `kitpip_verify` were already gone from this repository's DAG. The stale copies sit in cade and cade-infra | Change list below |
| Skipped stages | `nv run --stages` used to return ok with nothing run when a selected stage stayed stale behind an upstream outside the list. The row runs that command and reads ok as finished, so `handoff` could be skipped without a refusal. It now refuses `stage_input_stale`. A fresh stage or one the job turns off stays ok | `narrate/video/run.py` `input_refusal`, `test_a_selected_stage_with_a_stale_upstream_outside_the_limit_refuses`, `test_compose_and_handoff_on_a_changed_cut_compose_then_refuse` |
| Changed cut order | `compose`, `deliver_check`, `handoff`. Through the tools: compose, verify, compose with `handoff` true | Compose skill step 4, `narrated_video_compose` draft |

## Pin

| Field | Value |
| --- | --- |
| `row.tasks_sha256` | `c0be61edb1d38a42d49a37789f4e5c65c3f6fa9c370f7ff8342f872fbf1dc21b` |
| File blob | `4d272b4ea8a9d87ef2e11fdf1f6f79fd7035494d` |
| File sha256 | `8cefe6d88650bfe5ecbdc797abd6021bf3d41859848cae46f1fd108f45b598d4` |
| Commit on this branch | `6398671e3e7ae79738555fb6e7fdcee5d7185c1a` |

The digest is SHA-256 of canonical JSON: sorted keys, no whitespace, UTF-8, tasks in row order, each task's parents
sorted. A task holds `name`, `parents`, `optional`, `effect` and, on a stage task, `source_tool`.

The blob holds across a merge. The commit does not when a merge rewrites it, so the pin takes the commit that reaches
main.

Measured read-only on November 5, 2026, at cade-infra `08bf7706` and cade `7c83f547`. The catalog row and the pinned
graph both hash to `58e0a99a` as landed. Three repairs bring each to `c0be61ed`: `source_tool` of the task `avatar`
becomes `avatar_overlay`, `source_tool` of the task `avatar_check` becomes `avatar_verify`, and `deliver_check` joins
the parents of `handoff`. No other field differs. The task names stay `avatar` and `avatar_check`. Renaming the tasks
gives a different digest and breaks `VIDEO_STAGES` and `CLIENT_VIDEO_STAGES`.

## Changes for the cade and cade-infra owners

cade-infra `config/hatchet-workflows.json`, row `client-video-narrated-render`:

| Field | Change |
| --- | --- |
| `stage_graph.commit`, `stage_graph.blob` | The pin above |
| `tasks` | `source_tool` only: `avatar_overlay` on the task `avatar`, `avatar_verify` on the task `avatar_check`. Add `deliver_check` to `handoff.parents`. Task names do not change |
| `stage_graph.open_edge` | Delete. The edge is settled |
| `contract.asks` | Both entries are answered, so write `[]`. The event binding is `EVENT_TRIGGERS` in cade `src/hatchet-contract.ts`. The handoff question is settled above |
| `stage_graph.mapping` | Say that handoff waits on deliver_check, so a failed cut stops before it |
| `title`, `contract.status`, `rulings` | The row is general and cites `3672cb05`. The seven-task sentence goes |
| `blockers` GPU voice line | `--from-run` exists. Keep the part that says these are not tasks yet |
| `enforcement.worker_registration_gate.scope` | The cron-only sentence predates the event binding |

cade-infra `scripts/hatchet.py`: `VIDEO_STAGE_GRAPH`, `VIDEO_STAGES`, `VIDEO_EFFECT_NONE` and the comment above them.
A check that hashes the row's tasks and compares `tasks_sha256` would close the loop, since this repository cannot read
the catalog. `docs/hatchet.md` repeats the pin and the seven-task sentence.

cade:

| File | Change |
| --- | --- |
| `src/hatchet-contract.ts` `PINNED_TASK_GRAPHS` | The same three repairs: two `source_tool` values and the `handoff` parent |
| `src/hatchet-client-video.ts` `runStage` | Confirm a nonzero `nv run` fails the task, since a skipped stage now refuses. `nodes` empty with ok true still means fresh or turned off |
| `src/bs21-guard.ts` `EFFECT_NONE_TASKS`, `docs/BS21_GUARD.md` | `avatar_verify` |
| `tests/hatchet-bs21-registration.test.ts`, `tests/bs21-guard.test.ts` | Tool names and the handoff parent |
| `dhall/ClientVideoService.dhall`, `src/client-video-service.ts` | The seven-task `workflow`, `tasksFor` and the `prerendered_required` block are the last separate shape. Fold them into the pinned graph. Its `Edition` union also lacks Internal, which a general row needs |
| `docs/CLIENT_VIDEO_SERVICE.md` | "Not in the workflow" still lists `handoff` |
| `docs/HATCHET_CLIENT_VIDEO.md` | The sentence that says handoff does not wait on deliver_check |
| `config/artifacts/cade-infra-hatchet-workflows-45fb4fc` | Re-pin after cade-infra lands |

## Tests

The graph file ran first, then the whole narrate suite in 5 batches, each in its capped scope in the condense shell,
local and non-qualifying: 2698 passed and 1 skipped. `just narrate-dhall-check` passed with 96 mutations. 233 graph,
rerun and render stage tests passed on the merge with `feat/tin-7788-rerun-mixed-takes` at `d593c098`. Reverting the
refusal, dropping the edge, making it a digest edge, swapping two edition points or dropping `segments.avatar` each
fails a test, and the last two also fail `check.py`. The recorded handoff key matches the key computed at `e3761ee6`.
Bazel did not run.

## Open

- `narrate/video/render_stage.py` still binds `WORKFLOW = "cade-hardware-handoff"`, `EDITIONS_V1 = ("Internal",)` and
  `UNTIL = ("deliver_check",)`. The render stage runs `--until deliver_check`, so a general row that reuses it never
  reaches `handoff`. A general row changes all three. Owner: the narrate seat under TIN-7788, in a change after
  `feat/tin-7788-rerun-mixed-takes` lands, because that branch at `d593c098` edits the file and keeps all three. It
  must land before the first replay through the row, stage 7 of the staged path.
- `nv run` by hand still writes layers for a cut with a failed machine gate. Only the row stops there.
- A checkout of this repository cannot detect drift in the private catalog. The test binds the DAG to its recorded
  digest, and the catalog side needs the check above.
