# Rerun, FIX counter and mixed takes (November 5, 2026)

Linear TIN-7788, stages 9 and 11 of the narrated render path, video-utils half. Ruling TIN-7125 `3672cb05`: same job
folder, resume by a new event, stop after 3 FIX rounds and ask, spend cap per GPU window with no number set. Receipt
cites R-HOOK-CONVERGENCE-20261004 (R-N13). No new spec, Dhall type or catalog row. Nothing ran on a GPU.

`rerun | narrate lane | video-utils feat/tin-7788-rerun-mixed-takes | committed locally, checks below | root review, then draft PR on fix/tin-7994-lift-confidential`

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

## Open

- The answer to `fix_cap_reached` is not ruled (R9). A root stays stopped until the operator rules what continuing means.
- `gpu_window_not_v1` stays. `result` refuses `mixed` until the notice poster and the receipts exist (R3).
- Cade does not call `nv fix`, and its cap counts per packet (R10).
