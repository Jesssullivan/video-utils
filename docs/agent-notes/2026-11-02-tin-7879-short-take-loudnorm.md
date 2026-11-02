# Narrate: short-take loudnorm lands outside tolerance (2026-11-02)

Authority: Linear TIN-7879 under TIN-7788 and repository AGENTS.md. Receipt
per R-HOOK-CONVERGENCE-20261004 (R-N11, R-N12, R-N13). Measurements only. No
take, transcript or voice clip is in this note or its tests.

`TIN-7879 loudnorm | narrate seat lane | video-utils fix/tin-7879-loudnorm-short-take (from main 5a45d1ac) | fix, spec, README, synthetic tests; checks below | root review and merge`

## Cause

`audio.loudnorm` set its one linear gain from loudnorm's first-pass
`input_i`. On a 4 s take that reading disagrees with FFmpeg `ebur128`, the
meter `loudness_verdict` reads. On two synthetic 4 s takes the first pass read
within 0.05 LU of `ebur128` over the take with its last 3 s appended: the
analysis pass behaves as if its 3 s buffer is metered twice. A quiet tail reads
low and lands the take loud. A loud tail reads high and lands it quiet.

| Synthetic 4 s take at 48 kHz | `ebur128` | loudnorm first pass | delivered at main | delivered with fix |
| --- | --- | --- | --- | --- |
| head 0.6 s at 6000, tail at 2000 | -23.6 | -24.07 | -15.2 | -16.0 |
| head 1.2 s at 6000, tail at 3000 | -22.3 | -22.67 | -15.3 | -16.0 |
| head 1.0 s at 3000, tail at 6000 | not recorded | not recorded | -16.3 | -16.0 |

The limiter loop compounded the error because its headroom used the same
reading. The issue's run shows the same sign: a first pass of -24.49 against a
second-pass -23.87 and a delivered -15.4.

## Fix

`audio.integrated_lufs` reads `ebur128` integrated loudness through the
limiter chain to a thousandth of a LU. `loudnorm` passes it as `measured_I` and
uses it for the limiter's headroom. loudnorm's first pass still supplies the
true peak, range and threshold. The record adds `metered_input_i`. The
tolerance, `loudness_verdict` and the gate are unchanged.

## Checks

| Check | Result |
| --- | --- |
| new short-take tests at main's `audio.py` | 3 failed: `loudness_out_of_tolerance` at -15.2, -16.3 over the 0.1 check, no `integrated_lufs` |
| `just narrate-test` with the fix, `nix develop .#condense` | 2450 passed, 1 skipped |
| `ruff check` and `ruff format --check` on `narrate` | passed, 106 files formatted |
