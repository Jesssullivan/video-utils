# Narrate SIM lane: finish, bench wiring and the run-1 re-score (2026-10-26, TIN-7090)

Authority: operator ruling J83(a) of 2026-10-26 (no engine pick before SIM is measured and A3 is fixed); re-run
plan on TIN-7085 (comment 365540a1), steps 1 and 3. R-HOOK-CONVERGENCE-20261004: R-N11 (own tasks only), R-N12
(hooks advisory; huskycatd was absent and its needs were recorded as pending), R-N13 (this receipt and the tracker
comment). No TTS model ran on the shared CPU host. The GPU host was not touched. No sibling repository, session,
host or plugin configuration changed.

## What changed on `feat/narrate-mcp-tools` (PR #41)

| Commit | What |
| --- | --- |
| rebase | onto main `9242096` (the bench runner and `score.py`) |
| `fix(narrate): check consent before SIM and bound its interpreter, threads and length` | The open fix-round edits, kept after review: `policy.check_consent` split out of `check_voice`; SIM has no default interpreter; `[sim] threads` is an integer 1 to 8 (config refuses others); gate overrides only tighten; wSIM skips windows with under 3 s of voiced frames; the worker embeds at most 60 s per file; a worker past the tool deadline dies with its process group (new admission test). Host wording now matches the TIN-7085 rule: SIM on the shared CPU host runs one scorer at a time inside a 6G memory scope; no TTS model runs there |
| `feat(narrate): score bench SIM with wSIM and the preregistered decoy checks` | `narrate/bench/score.py`: `--sim-python`, `--sim-threads`; `--reference` is bound to the window's `inputs-verified.json` voice.wav sha256; per pass SIM median, minimum and wSIM over the joined chunks; decoy 1 (reference self-match) and decoy 2 (preset-voice passes); each pass read against the bench plan's SIM bars. `just narrate-bench-score - DEST` scores an already-pulled directory |
| `fix(narrate): gate SIM references and validate worker evidence` | Restores PR #45, see below |
| `fix(narrate): drop the decoy rows' PCM before the bench scorer writes JSON` | The second re-score crashed at the JSON write: decoys 4 and 5 kept the PCM the wSIM change added to each row. Dropped, with a test that runs the decoys beside SIM (it fails without the fix) |

## Incident: PR #45 overwritten and restored

PR #45 (the SIM security successor, merged into this branch on 10-24) was on the remote branch but not in this
worktree. The rebase push used `--force-with-lease` against the stale local tracking ref and replaced it. Found
right after the push by comparing the replaced head (`b45dcec`). Restored by cherry-picking `a810938` and merging
its semantics with the fix round: current consent and a matching reference clip before any store hashing or audio
read (now in `check_consent`, with type checks, `consent_invalid` and `ref_clip_changed`), and the strict worker
reply validation (exit 0, one finite cosine in [-1, 1] per requested id, positive durations, versions, threads).
`narrate/tests/test_sim_security.py` and its 10-24 note are back and pass. Lesson: fetch and compare the remote
branch before any force push, not only the base.

## SIM bars and where the measurements sit

The bars are the bench plan's preregistered ones (`docs/agent-notes/2026-10-22-narrate-bench-plan.md`, "Bars" and
"Decoys"); this lane implements them and does not move them:

- median chunk SIM at least 0.45 and at least 0.15 above the preset-voice decoy;
- wSIM minimum at least 0.8 times the median;
- decoy 1 (second half of the reference against its first half) "well above the bar", read as at least 0.60
  (bar plus margin); decoy 2 (preset voice) below the bar and at least 0.15 below decoy 1.

Synthetic measurements (registered model, formant voices of `narrate/tests/test_tools_sim.py`, no recording): same
tract 0.954; higher-pitch shorter-tract decoy 0.603; breathy longer-tract decoy 0.399. The near synthetic decoy
lands above the 0.45 bar, so the absolute bar alone does not reject a close voice; the margin over the real
preset-voice decoy does the work. The real-voice controls and the run-1 table are private and are on TIN-7090.

## Gates

| Gate | Result |
| --- | --- |
| `just narrate-lint` | passed |
| `just narrate-test` | 224 passed, 1 skipped (the opt-in real-model case) |
| opt-in real-model SIM test, 6G scope | passed |
| `tests/` S5/S4/S3/S2/S1 admission, MCP, public tree, bench host and fetch, bazel graph, share export, model prefetch | passed, except two local environment failures that also fail without this change: `test_tool_contracts` marked_video (fonts) and `test_web_runs_s3` build (offline pnpm mirror) |
| `narrate/tests/test_bench_score_sim.py` after the decoy fix | 4 passed; the new decoy test fails on the previous head |
| CI on PR #41 head `333c0e8` | green (offline, bazel, narrate, condense, web, site), both workflow runs |

Every local step ran inside `systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 nice -n 19 ionice -c3`
after a `/proc/pressure/memory` check.

## Run-1 re-score

Run 1 (`narrate-bench-20261023`, pulled on 10-23 and unchanged since) was re-scored from the local copy with
`just narrate-bench-score - DEST`: whisper small.en for WER, the registered ECAPA checkpoint for SIM with 4
threads, the window's own voice reference (sha256 matched against `inputs-verified.json`), and `--decoys`. It ran
inside the 6G scope at nice 19 / ionice idle, alone, after a memory-pressure check: 21 min wall, 1.1 GB peak
RSS. No audio left the private run directory; `scored.json` and `scored.md` were rewritten there and the
earlier scores are kept beside them.

Two attempts failed before the result, both on scorer code from this lane and both after about 21 to 24 minutes
of scoring: a crashed smoke with no chunk reached the bars without a wSIM (fixed in `20ff4ea`), then the decoy
rows' PCM reached the JSON write (fixed in `333c0e8`). The SIM interpreter's store path had also been collected
between the 10-26 attempts; the `ml` shell is now rooted by a profile outside the repository.

Outcome (numbers on TIN-7090):

- decoy 1 (reference self-match) and decoy 2 (the preset-voice pass, a different speaker) are both valid; the
  different speaker scores far below the bar and below decoy 1, so the bars are usable for this run;
- decoys 4 (half silence, reversed) and 5 (shuffled transcript) stay valid;
- A2 meets every SIM bar on both seeds and its smoke;
- A1 meets the median and decoy-margin bars on both seeds; its seed 2 misses the wSIM bar (window minimum
  under 0.8 times the median), so A1 has at least one weak 10 s stretch;
- A3 produced no audio (the smoke crash J83(a) names), so it has no SIM; the A3 fix and its window are another
  lane's.

These are measurements against one reference clip on one microphone. They are not listening acceptance and do not
pick an engine; the J83(a) re-run still needs A3 working before any pick.

## Open

- Decoy 3 (espeak-ng robot baseline) and UTMOS are still not scored, so two scorer checks of the plan are missing.
- Window 2 with two voices: `score.py` takes one `--reference`, bound to the window's single voice.wav.
- SIM per take inside render stays unwired (`sim_not_measured`); `minSim` stays uncalibrated in jobs.
- A SIM number is not listening acceptance; the operator's blind A/B decides the pick.
