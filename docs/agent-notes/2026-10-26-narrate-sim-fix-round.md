# Narrate SIM lane: review fix round (2026-10-26, TIN-7090)

Authority: operator ruling J83(a) of 2026-10-26 (no engine pick before SIM is measured and A3 is fixed); re-run
plan on TIN-7085 (comment 365540a1). R-HOOK-CONVERGENCE-20261004: R-N11 (own branch and worktree only), R-N12
(hooks advisory; huskycat queued its needs to huskycatd and continued), R-N13 (this receipt and the tracker
comment). No TTS model ran on the shared CPU host. Every test, lint and mutation run used a fake SIM worker and ran
one at a time inside `systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 nice -n 19 ionice -c3`, after
a `/proc/pressure/memory` check. No whisper or SIM model ran. The GPU host was not touched.

The review of PR #41 at `fb90fc7` found no blockers, 3 majors and 7 minors. This round fixes all of them on the
same branch, or records why a finding needs a note rather than code.

## Dispositions

| # | Finding | Disposition |
| --- | --- | --- |
| 1 | One chunk over 60 s, or any worker error, set the bench scorer to `None` for the rest of the run | Fixed. A chunk over the worker's 60 s gets `sim_skipped: too_long` and is never sent, so the rest of its pass still scores. A worker failure leaves only that pass `not_measured` (with the worker's reason). A decoy-1 failure leaves only decoy 1 unmeasured. The scorer stays up. Tests: a 61 s chunk, and an arm whose worker request fails, scored before an arm that measures |
| 2 | The fake worker returned one score per class, so the bar logic was untested | Fixed. The fake worker looks up a score for each file by its scratch name (arm, pass, chunk or window). Like the real worker it refuses a file over 60 s. It also refuses a wSIM window over 10 s, a chunk not paired with the reference, and a decoy-1 pair that is not the second half against the first. Tests now cover: a weak window under 0.8 times the arm median; a median under 0.45; a median within 0.15 of decoy 2; decoy 2 within 0.15 of decoy 1 while under the bar; both boundaries; silent windows (2 skipped, the exact starts asserted); and a missing decoy 2. Exact bar values are asserted. 15 mutations of `score.py`, each run on its own, all fail the suite. They include the reviewer's six (`wsim_ok` forced, `median_at_least_bar` forced, decoy margin removed, silent skipping off, whole-track windows, first half against itself) and nine more (every decoy counted as decoy 2, smoke counted, long-chunk skip off, scorer dropped on failure, `over_decoy_ok` forced, None counted as met, consent check skipped, reference sha binding skipped) |
| 3 | `narrate_evaluate` started whisper and torch with no memory scope and no lock | Fixed. On Linux, `narrate_evaluate` with `wer` or `sim` starts `python -m narrate evaluate` behind `systemd-run --user --scope --quiet --collect -p MemoryMax=6G -p MemorySwapMax=0 nice -n 19 ionice -c3`. If a probe cannot make that scope, those metrics are refused with the probe's reason, and they never start unscoped. Loudness and overruns need no scope. Off Linux there is no prefix. `narrate evaluate` holds a host-wide flock (`narrate.sim.scorer_lock`, under `$XDG_RUNTIME_DIR`) while whisper or the SIM worker runs. The bench scorer holds the same lock for its whole run. While another scorer holds it, wer and sim are `not_measured` (the bench scorer exits 2), and nothing is queued. Tests: the scope argv, the probe refusal, missing tools, macOS, and a held lock |
| 4 | Every decoy pass counted as decoy 2 | Fixed. Only passes whose decoy id starts with `decoy2` (host-job.json's `decoy2-preset-UK_George`) set decoy 2. A `decoy3-*` pass that scores high is in the test |
| 5 | wSIM had no mean; a pass with no windows gave `wsim_ok: None` with no reason; "met" was decided by hand | Fixed. wSIM reports min, mean and every window (start and score). An empty wSIM gives a reason: no chunk audio, mixed sample rates, or every window silent. Each arm has `bars.all_met` and `bars.unmet`, where any bar that is not True (None included) is unmet, and so is decoy checks that are not both valid |
| 6 | Bars were read per pass, but the plan reads them per arm; A2's margin used A1's decoy | Fixed. The bars are read per arm, over the chunks and wSIM windows of its seed passes. Smoke passes repeat a seed-1 chunk and decoys are another speaker, so neither counts. The wSIM ratio uses the arm's median. Passes keep their measurements but carry no bars. Decoy 2 stays bench-wide on purpose: the plan makes it once, inside A1-gpu's budget, as "the decoy the SIM bar is defined against". The check now records which arms supplied it. This is the plan's design, not a deviation |
| 7 | `SIM_SELF_MIN = 0.60` is a reading of "well above the SIM bar" | Noted. The constant's comment, the check's `expected` text and the TIN-7085 comment all state that 0.60 (the bar plus the margin) is an interpretation, not a preregistered number |
| 8 | The bench scorer embedded `--reference` without a consent check | Fixed. A new `--config narrate.toml` is required for SIM. Every registered voice whose `refClipSha256` is the clip's sha256 must pass `policy.check_consent` for the config's job scope. The registry is checked first, then the store, which must hold the clip and the consent evidence. This happens before the clip is decoded. Without `--config`, SIM is `not_measured` (`consent_unchecked`). A revoked consent gives `consent_revoked`, and an unregistered clip gives `voice_unknown` |
| 9 | `narrate evaluate` passed an empty run, and one long chunk sank the whole request | Fixed. A run with no chunks is `not_measured`. A chunk over 60 s is listed with `sim: null, skipped: too_long` and the others score in the same request. `passed` is None (no verdict) while any chunk is skipped or none scored |
| 10 | Smoke rows copy seed 1's first chunk; SIM is scored against the clip that conditioned the clone | Noted. Smoke passes no longer count toward an arm. The second point is a limitation of the method, not of the code: every SIM number here compares a render with the clip that conditioned it. The shared recording channel can inflate scores, so the numbers are not evidence of how a listener hears the voice |

## Run 1 read against the per-arm bars

The private `scored.json` of run 1 was read without changing it, and each arm was recomputed over its seed passes
(numbers on TIN-7090). The verdicts are the same as the per-pass reading: A2 meets every SIM bar; A1 meets the
median and decoy-margin bars but misses the wSIM bar at arm level, because one window of its seed 2 is under 0.8
times the arm median; A3 has no audio. Run 1 had only one decoy-2 pass, so finding 4 changed nothing there.
The wSIM mean needs a re-score, because the old file kept only per-pass minimums.

## Gates

| Gate | Result |
| --- | --- |
| `just narrate-lint` | passed |
| `just narrate-test` | 238 passed, 1 skipped (the opt-in real-model case) |
| `tests/test_s5_tool_admission` | 11 tests OK (one new: the scope) |
| S1, S2, S3, S3g, S4a, S4b admission and `test_mcp` | 101 tests OK |
| `tests/test_public_tree.py` | 3 passed, 1 skipped |
| Mutation run on `score.py` | 15 of 15 killed |

## For the J83(a) re-run

The bench score command now needs `--config` pointing at the narrate.toml that registers the window's voice. It
also takes the one-scorer lock, so an evaluation in progress makes it exit 2 instead of overlapping. Decoy 3
(espeak-ng), UTMOS and the two-voice window are still not scored, and `minSim` is still uncalibrated.
