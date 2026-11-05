# Rerun, FIX counter and mixed takes (November 5, 2026)

Linear TIN-7788, stages 9 and 11 of the narrated render path, video-utils half. Ruling TIN-7125 `3672cb05`: same job
folder, resume by a new event, stop after 3 FIX rounds and ask, spend cap per GPU window with no number set. Receipt
cites R-HOOK-CONVERGENCE-20261004 (R-N13). No new spec, Dhall type or catalog row. Nothing ran on a GPU.

`rerun | narrate lane | video-utils feat/tin-7788-rerun-mixed-takes | review findings applied, base e3761ee6 merged, checks below | draft PR on fix/tin-7994-lift-confidential`

## What changed

| File | Change |
| --- | --- |
| `narrate/video/rerun.py` | the render ledger `JOB/rerun.json`, the proof of what ran and the FIX counter |
| `narrate/video/store.py` | `current.json` counts commits, and each stage entry holds its `seq` |
| `narrate/video/render_stage.py` | `mixed` voice mode, optional `rerun` and `spend`, the `takes` action and `rerun` in the result |
| `narrate/video/bundle.py`, `narrate/video/cli.py` | `intake --replace`, `fix` and `render-stage takes` |
| `docs/spec/RENDER_STAGE.md`, `docs/spec/NARRATED_VIDEO.md` | the "Reruns" section, the commands and the rerun table |
| `just/narrated-video.just`, `narrated-video-verify` skill | `nv-fix`, `nv-render-stage-takes` and a pointer |
| `narrate/tests/test_narrated_video_rerun.py` | fake-runner tests and real-stage tests on the synthetic bundle |

## Decisions in this draft

- `ran` reads a commit counter, not stage keys alone. A forced rerun of an unchanged key therefore shows as `repeated`.
- A FIX round is one recorded decision on one cut. The third FIX still gets its rerun, and the fourth refuses. Cade's
  routed-cuts cap reads the same way.
- The spend check is `lease.max_seconds` at the caller's rate against the caller's cap. The window is time-capped, so
  that ceiling needs no estimate of voicing time.
- `rerun` and `spend` are optional keys at schema version 1, so a `from_run` request written before them stays valid.

## Review of d593c098

Verdict FIX. Eleven probes and 22 hand mutants. Each finding, and what changed:

| Finding | Change |
| --- | --- |
| A FIX did not bind the gate | `accept` reads `rerun.json`: the FIX decision refuses `decision_bound_elsewhere`, and a new decision on that cut refuses `cut_sent_back` |
| FIX decisions were unique to one job | `bound_elsewhere` scans every job's `rerun.json` under the root lock |
| `fix_unchanged_cut` read only the previous row | `result` checks the cut against every round. A FIX with no render row binds its cut too, and the next render answers it |
| `revoice_unneeded` did not hold before spend | `takes` refuses every fresh null by default. `--after-window`, the `voice_ready` phase, alone shows `revoiced` |
| A changed beat named with its old take passed | `takes` refuses `voice_run_mismatch` on a stale node that holds the named take. The spec says other takes are checked after spend |
| A reused event skipped the request | `result` compares `request_sha256` and refuses `rerun_event_reused` |
| `intake --replace` did not bind the job | It refuses `job_mismatch` when the earlier intake wrote another job |
| The retired intake returned on `OSError` only | The restore moved to the outer `except BaseException` |
| `takes` docstring drift | Corrected: a `gpu_window` voices every beat, so a fresh one refuses |
| 10 surviving mutants | New tests cover each one |

## Checks

Run through the lane's capped test wrapper in the `condense` dev shell, on the synthetic fixtures. No GPU ran.

| Check | Result |
| --- | --- |
| `test_narrated_video_rerun.py` | 78 passed |
| All `test_narrated_video_*` files | 1697 passed |
| The rest of the narrate suite | 1059 passed, 1 skipped |
| `ruff check` and `ruff format --check` in `narrate/` | clean |
| 18 hand mutants: the review's 10 survivors, one fix-path mutant per finding | 18 killed by their named tests |

## Open

- The answer to `fix_cap_reached` is not ruled (R9). A root stays stopped until the operator rules what continuing means.
- `gpu_window_not_v1` stays. `result` refuses `mixed` until the notice poster and the receipts exist (R3).
- Cade does not call `nv fix`, and its cap counts per packet (R10).
- `rate_usd_cents_per_hour` 0 passes for any engine, so a rented window can declare 0. Bind rate 0 to an on-prem engine
  before `gpu_window_not_v1` lifts.
- A take the node never held is checked at `voice_adopt`, after `voice_gpu`. Only the two take checks in "Mixed takes"
  come before spend.
