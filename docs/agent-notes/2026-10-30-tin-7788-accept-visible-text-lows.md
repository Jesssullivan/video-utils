# Narrated video: low findings from the accept and visible-text reviews (2026-10-30)

Authority: Linear TIN-7788 and repository AGENTS.md. The lane fixes the low
findings left by the final reviews of PR #76 (`fc0eca97`) and PR #77
(`44231111`). Receipt per R-HOOK-CONVERGENCE-20261004 (R-N11, R-N12, R-N13).

`accept/visible-text lows | narrate-dispatched lane | video-utils fix/tin-7788-accept-visible-text-lows-20261030 (from main 44231111) | six fixes, spec, skills, synthetic tests; checks below | root review and merge`

## What changed

| Finding | Fix | Files |
| --- | --- | --- |
| `status` trusted `graph.json`'s operator view | `check_recorded` recomputes `accepted` and `pending_operator` from `job.json`, admit's list, the current `deliver_check` render and `acceptance.json`. It refuses `graph_stale` when the recorded ones differ, when admit drops a gate `job.json` opens or the render reports, and when `deliver_check` shows `fresh` while admit holds a gate at it | `accept.py` |
| `accept` paired a new `job.json` with an old render | `deliver_check` keys on the job's digest, and `render_of` refuses `deliver_check_stale` when the render's `job_sha256` knob is not the digest of `job.json` on disk | `graph.py`, `accept.py` |
| A malformed `graph.json` was skipped after the row was written | `refresh_graph` checks the graph's shape and returns the refreshed document before `acceptance.json` is written. A malformed graph refuses `store_invalid`, a directory `store_invalid` and a symlink `stage_symlink`, with nothing recorded | `accept.py` |
| No test showed `deliver_check` back at `fresh` | the visible-text acceptance test asserts it in the plan, the recorded graph and `status` | `test_narrated_video_accept.py` |
| A CSS escape in a presentation attribute was not opaque | a backslash in any attribute other than a label makes the SVG opaque, as in `style` | `visible_text.py` |
| `intake.json` `admit.pending_operator` missed `visible_text_unread` | the intake passes its own visible-text summary to admit, so the gate is listed exactly when `states.visible_text` is `partial` | `bundle.py` |

## Review follow-up

The review of `0c1ddaee` found five issues. New commits on the same branch fix
them.

| Finding | Fix | Files |
| --- | --- | --- |
| A backslash in metadata made an SVG opaque, such as `inkscape:export-filename` or `data-unformatted` | the backslash, `@import` and `image()` rule reads only attributes in no namespace that are not `data-*`. A `url()` still counts in every attribute | `visible_text.py` |
| A gate whose `segment` was a list crashed `status` untyped | `graph_shape` requires a segment that is a string or null, so it refuses `store_invalid` | `accept.py` |
| `status` passed a graph with no `deliver_check` node | `check_recorded` requires the node ids `job.json` gives. The spec no longer says a hand edit cannot hide a gate | `accept.py`, spec |
| The key table said `delivery except handoff` | the row names the job's digest, which covers all of delivery with `handoff` | spec |
| `image-set()` and `image()` load a file from a plain string | `external_css` treats both as external, `-webkit-image-set()` included | `visible_text.py` |

Upgrade: the `deliver_check` key now includes the job's digest, so every render
keyed before this change is stale. Acceptance rows recorded before it bind
nothing after `deliver_check` reruns. The operator records the same decision
again for the same cut.

Mutation probes of the follow-up, each reverted after the run:

| Probe | New tests failing |
| --- | --- |
| gate segment type not checked | 2 |
| node set not checked | 1 |
| backslash read in metadata attributes | 2 |
| `image-set()` and `image()` not external | 3 |

Checks of the follow-up:

| Check | Result |
| --- | --- |
| narrate pytest, run through tinyland-heavy | 2227 passed, 1 skipped |
| ruff check and format | clean |
| stdlib smoke, repository root on the path | 7 tests OK |
| `tests/test_public_tree.py` | 4 passed, 1 skipped |

## Choice for review

Keying `deliver_check` on the job's digest changes one tested row: turning
handoff on now reruns `deliver_check` as well as `handoff`. The alternative, a
digest in the manifest outside the key, would leave `plan` showing a fresh
`deliver_check` that `accept` refuses, with `run --force` as the only way out.
The rerun opens listening and lip sync for the new render, and `accept` records
the same decision again for the same cut, as after a bed record update.

## Checks

Mutation probes, each reverted after the run:

| Probe | New tests failing |
| --- | --- |
| intake admit without this intake's summary | 2 |
| presentation attributes read as before | 2 |
| `render_of` without the job check | 1 |
| `status` without the `accepted` comparison | 1 |
| `status` without the `pending_operator` comparison | 2 |
| graph refresh after the `acceptance.json` write | 4 |

Suite results are in the PR body.

## Open

- `status` reads no records. It checks the bed and visible-text gates through
  the current `deliver_check` report, so a gate the records open after that
  render shows only after the next `plan --record`.
- `graph.json` carries no signature. An edit that rewrites the `deliver_check`
  node's key and state and drops a records gate from both lists still passes
  `status`. `plan` recomputes every state from the store and the records.
  Removing the node now refuses `graph_stale`.
- The `Huskycat-Receipt` trailer that the commit hook writes names the host.
  The lane keeps hook trailers as the brief says. Earlier commits on main
  carry the same trailer.
