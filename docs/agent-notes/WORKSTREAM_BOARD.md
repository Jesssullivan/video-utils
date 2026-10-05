# video-utils parallel work board

As-of ownership checkpoint: **2026-10-05 22:43:49 UTC / 6:43:49 p.m. EDT**.
Root's goal began 20:49:34 UTC and remains **active**, with planned end
**2026-10-06 06:49:34 UTC / 2:49:34 a.m. EDT**. Objective/status does not enforce
this wall-clock horizon. Root owns integration, factual Linear writes and signed
publication. This repository-local board does not replace the global Lab board.

Authority: operator ten-hour parallel goal; repository AGENTS.md;
R-HOOK-CONVERGENCE-20261004 / R-N11/R-N12/R-N13, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`.

Plan: [TEN_HOUR_PLAN.md](../spec/TEN_HOUR_PLAN.md).
Prompts: [2026-10-05-user-prompts.md](2026-10-05-user-prompts.md).
Checkpoints: [2026-10-05-goal-checkpoints.md](2026-10-05-goal-checkpoints.md).
Tracker IDs: [linear.json](../../program/linear.json).
Active goal: [TIN-5495](https://linear.app/tinyland/issue/TIN-5495/ten-hour-parallel-guitar-toolkit-implementation-goal).

## Published twenty-tool source

Signed/private/verified source **`45a1313ccbcb0ecc097f3a017979254e5719a3c6`**
is published. It contains **twenty hooks and twenty skills**, including read-only
corpus-metadata validation. Local integration passed **291 tests in 53.583 s,
no skips**, plus 47 hook-focused checks. Hosted CI
[37383660576](https://github.com/Jesssullivan/video-utils/actions/runs/37383660576)
**completed successfully at 22:38:45 UTC** per root's exact readback. Earlier
5f35a14/6f7d196 success belongs to their own revisions, not this result.

## Released calibration code ownership

Root released the next **five code/interface lanes** after 45a1313 publication.
Their earlier plan-only freeze is lifted for the exact named files below. Later
explicit assignments add a pilot executor, read-only audit and plan-only native
lane. Other workers remain idle/done by default. The goal continues;
assignment does not establish implementation, scores or publication.

| Stream | Owner | Exclusive assigned files | State / dependency |
| --- | --- | --- | --- |
| Generated bank | `/root/repo_patterns` | `scripts/benchmark.py`, optional new `scripts/benchmark_bank.py`; `tests/test_benchmark.py`, optional new `tests/test_benchmark_bank.py`; optional new `program/benchmarks-v2.json`, BENCHMARK_CALIBRATION_LANE | Code released; ≤12 fixtures/120 source seconds; preserve existing benchmarks.json bytes and v1 hashes; generator-only truth/bank index precedes evaluators |
| Pitch evaluator | `/root/guitar_features` | New `scripts/pitch_evaluate.py`, `tests/test_pitch_evaluate.py`; PITCH_CALIBRATION_LANE and owned dated evaluator receipts | Code released; four-job/30-source-second pilot; depends on generated bank/pilot index; retain coverage, octave/voicing and transition exclusions |
| Phrase evaluator | `/root/phrase_dag` | New `scripts/phrase_evaluate.py`, `tests/test_phrase_evaluate.py`; PHRASE_CALIBRATION_LANE and owned dated evaluator receipts | Code released; independent boundary/span/recurrence/warp metrics; labels withheld from discovery; depends on generated truth/artifacts |
| Tool contracts | `/root/tool_hooks` | `program/tools.json`, `scripts/tool_api.py`, `tests/test_tool_contracts.py` and existing owned contract docs/tests | Registry/API/schema ownership; agree evaluator inputs/results before integration; current published count remains 20 |
| Calibration skills | `/root/tool_skills` | Three calibration skills under existing owned `.agents/skills/**`; owned extension guidance | Depends on actual contracts/knobs; match benchmark and both evaluator intents; validation before publication |
| Calibration pilot worker | `/root/media_latency` | New `scripts/calibration_pilot.py`, `tests/test_calibration_pilot.py`, `docs/spec/CALIBRATION_PILOT_LANE.md` | Active explicit source assignment transferred from root; bounded orchestration depends on bank/evaluator contracts; root retains recipes, actual pilot run, integration/publication |
| Independent contract audit | `/root/audio_research` | New dated calibration-contract review under `docs/agent-notes/`; worker source/specs read-only | Active independent audit; record findings/evidence in owned review note; no worker/spec mutation |
| AU parameter-state integration | `/root/au_architecture` | New `docs/spec/AU_PARAMETER_STATE_INTEGRATION_LANE.md` only | Active PLAN ONLY before any native-file assignment; existing native code remains frozen |
| Integration/publication | `/root` | Shared recipes/source integration, real bank pilot, tests, Linear and signed publication | Run bounded actual synthetic bank/pilot and integrate receipts; distinguish fixture quality from real performance |
| Durable checkpoint | `/root/goal_plan` | This board, checkpoint log and TEN_HOUR_PLAN on explicit follow-up | Updated/frozen after handoff for root's selected doc receipt publication |

**Twenty-two tools are planned once both evaluator tools are live; not current.**
New source and skills require meaningful checks and root publication/readback.
This continues the same ten-hour horizon and weekly budgets without duplicate
hours or phantom workers. Authority: root's explicit release/assignment under the
operator's goal and R-HOOK-CONVERGENCE-20261004/R-N11/R-N12/R-N13.

## Actual complete existing-run evidence

Media run: `artifacts/runs/20261005T211103Z-c6d0bac2fcd2`.
New complete invocation:
`demo-invocations/20261005T221943Z-9f2a37bcca5c/receipt.json`.
All **fifteen stages completed**; selected clicks/pitch/meter/tonal/comparison
artifacts are **verified** for provenance. Original source, master and video
hashes remain unchanged; **no encoder ran** in this invocation. Verification
is artifact lineage, not musical correctness. Meter/tonic/mode remain unknown;
sparse pitch coverage and metronome uncertainty remain visible.

Current graph/report/markers have **197 ungraded review flags**, including
**eleven DTW comparison flags**. Earlier 186 flags belong to the retained prior
analysis. Prior source-history snapshot:
`demo-history/c9166c0152bb8be0fca4ed1dd048025c4e98c9bd713994669cb203a9bc145867`,
**14,181,050 bytes**, no media copied, explicitly
`prior_artifact_snapshot_not_revalidated`. Historical snapshot retention does
not promote prior artifacts into the current verified selection.

Existing accepted numerical export remains master −18.01 LUFS/−1.50 dBTP and
final decoded AAC −18.07/−1.56 after −0.06 dB feed, with 1102-sample calibrated
processing-delay compensation. Listening is pending; no whole-take transcription,
intended-note verdict or confirmed performance error is claimed.

Muted browser proof: all four media players loaded; 0.624 seconds/45 decoded
frames; filter 197→11, source-time seek, mobile 390px without overflow, no exceptions.
No actual-take review notes were written. Root's exact owned Chrome process 37154
was cleanly terminated with R-N11 receipt. Browser function is not listening
acceptance. Corpus validation retains supplied reviewer assertions and does not
establish musician truth. Native parameter-state/root-release ASan checks passed;
no plugin installation, auval or Logic hosting occurred. Editor-marker work is
source/fixture design without application-import acceptance.

## Historical CI and tracker boundaries

Run 37373112479 failed one parser-nesting test. Repair 9883069's run 37373960394
had no job steps; exact annotation: “job was not acquired by Runner of type hosted
even after multiple attempts”. The later 6f7d196 CI passed as recorded above;
keep runner acquisition, source tests and current pending publication distinct.

D0 TIN-5485 remains In Review for listening; current publication comment
`44694369-4105-4fad-814d-eea730c867c8`. Goal TIN-5495 remains In Progress;
comment `83ef0855-6b81-4b76-9a96-4911f58216ba`. Root updated/read back the project
and comments and synchronized program/linear.json to 45a1313/20/291/197. Root also
updated cached CI metadata/comments to the completed SUCCESS readback.
Publication/CI do not complete listening/native/editor states
or the goal. Planned end remains **2026-10-06 06:49:34 UTC**.
