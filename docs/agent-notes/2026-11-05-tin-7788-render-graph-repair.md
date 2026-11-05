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

## Pin

| Field | Value |
| --- | --- |
| `row.tasks_sha256` | `c0be61edb1d38a42d49a37789f4e5c65c3f6fa9c370f7ff8342f872fbf1dc21b` |
| File blob | `4d272b4ea8a9d87ef2e11fdf1f6f79fd7035494d` |
| File sha256 | `8cefe6d88650bfe5ecbdc797abd6021bf3d41859848cae46f1fd108f45b598d4` |
| Commit on this branch | `a3d892361a892b6426c54fb33e8b922182dc2eca` |

The digest is SHA-256 of canonical JSON: sorted keys, no whitespace, UTF-8, tasks in row order, each task's parents
sorted. A task holds `name`, `parents`, `optional`, `effect` and, on a stage task, `source_tool`.

The blob holds across a merge. The commit does not when a merge rewrites it, so the pin takes the commit that reaches
main.

Measured read-only on November 5, 2026, at cade-infra `08bf7706` and cade `7c83f547`. The catalog row and the pinned
graph both hash to `58e0a99a` as landed. Three repairs bring each to `c0be61ed`: `avatar_overlay`, `avatar_verify`
and `deliver_check` among the parents of `handoff`. No other field differs.

## Changes for the cade and cade-infra owners

cade-infra `config/hatchet-workflows.json`, row `client-video-narrated-render`:

| Field | Change |
| --- | --- |
| `stage_graph.commit`, `stage_graph.blob` | The pin above |
| `tasks` | `avatar` to `avatar_overlay`, `avatar_check` to `avatar_verify`, add `deliver_check` to `handoff.parents` |
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
| `src/hatchet-contract.ts` `PINNED_TASK_GRAPHS` | The same three repairs |
| `src/bs21-guard.ts` `EFFECT_NONE_TASKS`, `docs/BS21_GUARD.md` | `avatar_verify` |
| `tests/hatchet-bs21-registration.test.ts`, `tests/bs21-guard.test.ts` | Tool names and the handoff parent |
| `dhall/ClientVideoService.dhall`, `src/client-video-service.ts` | The seven-task `workflow`, `tasksFor` and the `prerendered_required` block are the last separate shape. Fold them into the pinned graph. Its `Edition` union also lacks Internal, which a general row needs |
| `docs/CLIENT_VIDEO_SERVICE.md` | "Not in the workflow" still lists `handoff` |
| `docs/HATCHET_CLIENT_VIDEO.md` | The sentence that says handoff does not wait on deliver_check |
| `config/artifacts/cade-infra-hatchet-workflows-45fb4fc` | Re-pin after cade-infra lands |

## Tests

Each batch ran in its capped scope in the condense shell, local and non-qualifying, because one run of the whole suite
hit the 600 second cap. 125 graph tests, then 231, 457 and 2000 with 1 skipped: all passed. `just narrate-dhall-check`
passed with 93 mutations. Bazel did not run.

## Open

- `narrate/video/render_stage.py` still binds `WORKFLOW = "cade-hardware-handoff"` and `EDITIONS_V1 = ("Internal",)`.
  A general row changes both. This lane left them for the rerun and mixed-takes lane.
- `nv run` by hand still writes layers for a cut with a failed machine gate. Only the row stops there.
- A checkout of this repository cannot detect drift in the private catalog. The test binds the DAG to its recorded
  digest, and the catalog side needs the check above.
