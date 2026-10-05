# video-utils parallel work board

As-of integration snapshot: October 5, 2026, 21:49:26 UTC / 5:49:26 p.m. EDT.
Root's observed run/test receipts are distinguished from pending publication.
Root's observed goal start is 20:49:34 UTC; the planned ten-hour end is October 6,
06:49:34 UTC / 2:49:34 a.m. EDT. The active objective/status mechanism does not
itself enforce a time deadline. This repository-local board does not replace the
global Lab board. Root owns integrated status and refreshes observed handoffs.

Authority: operator-approved parallel implementation and ten-hour goal;
R-HOOK-CONVERGENCE-20261004 / R-N11/R-N12/R-N13, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`.

Plan: [TEN_HOUR_PLAN.md](../spec/TEN_HOUR_PLAN.md).
Prompts: [2026-10-05-user-prompts.md](2026-10-05-user-prompts.md).
Checkpoint log: [2026-10-05-goal-checkpoints.md](2026-10-05-goal-checkpoints.md).
Project/issue IDs: [linear.json](../../program/linear.json).
Active goal: [TIN-5495](https://linear.app/tinyland/issue/TIN-5495/ten-hour-parallel-guitar-toolkit-implementation-goal).

| Stream | Owner | Repo / branch | State / evidence | Next |
| --- | --- | --- | --- | --- |
| Integration/publication | `/root` | `video-utils` / `main` | Final nineteen-tool suite: 219/219 passed in 160.966 s; wave2 source publication pending; hosted repair CI unverified | Publish selected verified source, then record remote/CI readback; listening and native hosting separate |
| Cleaned demo | `/root` | `video-utils` / `main` | Calibrated run `20261005T211103Z-c6d0bac2fcd2`: master −18.01 LUFS/−1.50 dBTP; final decoded AAC −18.07/−1.56 after −0.06 dB feed; strict target verified | Publish repaired measured iteration; retain first failure history; listening pending |
| Media processing latency | `/root/media_latency` | `video-utils` / `main` | 1102-sample calibrated compensation and bounded AAC-headroom retry verified in current run; final encoded target passes | Preserve executable/profile provenance and synthetic timing checks; real-performance ground-truth alignment remains unmeasured |
| Rhythm/tempo/clicks | `/root/rhythm_analysis` | `video-utils` / `main` | New-run fallback 88.800907 BPM / double 177.6018; operator 178 separate; direct seed abstained; click lane active | Measured click candidates/attenuation and attack preservation; no default click removal or verified metronome identity claim |
| Automatic features/pitch | `/root/guitar_features` | `video-utils` / `main` | Current 48 regions/14 recurrence pairs; sparse pitch sampled 20 seconds including ending; intended notes unknown | Publish source-bound candidate excerpts; do not promote sparse coverage into whole-take transcription |
| Meter inference | `/root/meter_inference` | `video-utils` / new tools | Meter worker included in 219-test local suite; actual meter remains unknown | Publish qualified hypotheses and abstention; no time-signature confirmation |
| Tonal inference | `/root/tonal_inference` | `video-utils` / new tools | Tonal worker included in 219-test local suite; actual tonic/mode remains unknown | Publish nullable evidence and limitations; no tonal or intended-note verdict |
| Phrase DAG/comparison | `/root/phrase_dag` | `video-utils` / `main` | New calibrated artifacts: 186 flags; comparator 21+markers 6 tests passed; earlier real pilot 10 alignments/4159 cells/0.109 s with 9 rate/shift hypotheses; attack edits abstained | Marker upstream-staleness repair; preserve main flags; root verifies new tool before publication |
| Typed tool extensions | `/root/tool_hooks` | `video-utils` / `main` | Nineteen hooks/skills in verified local integration; full 219-test suite passed; wave2 source not yet published | Root stages/publishes tested bundle and records readback; hosted CI remains separate |
| Tool skill extensions | `/root/tool_skills` | `video-utils` / `main` | Nineteen repository skills matched local tool integration; wave2 publication pending | Retain validated intent/knob/evidence guidance; root publication receipt |
| Graphical evidence review | `/root/plan_review` | `video-utils` / `main` | Actual browser muted playback/filter/decode passed; synthetic annotation edit/refresh passed; no dummy annotations in actual take | Preserve synthetic-vs-real annotation boundary; listening acceptance still pending |
| Research/spec/docs | `/root/clip_baseline` | `video-utils` / `main` | New research assignment FOSS_AUDIO_MATRIX and RESEARCH_LANE | Primary-source FOSS comparisons with licensing/applicability to distorted nine-string guitar |
| Benchmark/annotation | `/root/repo_patterns` | `video-utils` / `main` | Post-fix three standard-library+three optional cases: zero candidate shift, click recall 1; optional phrase IoU 0.935; synthetic evidence only | Retain old failure history; root publishes reproducible metrics without real-recording quality claim |
| Native AU architecture | `/root/au_architecture` | `video-utils` / `main` | Initial compiled ARC audit and root native recipe passed; next only automation/** +AU_AUTOMATION; existing native code frozen until publication | Isolated automation experiment; no installation/auval/Logic proof |
| Independent release review | `/root/release_review` | `video-utils` / read-only first release | Review completed; no release blockers reported; marker upstream-staleness improvement assigned to DAG owner | Verify follow-up and separately review new tools |
| Durable goal/prompts | `/root/goal_plan` | `video-utils` / `main` | Final prepublication board/checkpoint refreshed; documentation lane frozen after handoff | Root stages selected receipts; further edits require follow-up; goal remains active |
| Additional lanes | Unassigned | `video-utils` / isolated files required | No further assignment claim | Root records owner, files, acceptance and dependencies before delegation |
| Listening/AU/editor acceptance | Operator / future lane | Local run / future host | Listening pending; AU/Logic and native FCP/Resolve import unverified | Audition media and separately validate actual host/application acceptance |

First-release local evidence: 108 full Python tests and 27 targeted strict-JSON
checks passed without skips under the proper FFmpeg environment; seven Rust
tests passed earlier. Hosted CI
[37373112479](https://github.com/Jesssullivan/video-utils/actions/runs/37373112479)
failed one nesting-depth test after 109 tests with three optional-backend skips.
Local success is not hosted success. Deterministic repair now passes 28 targeted
checks under actual Python 3.14.6 and is published as signed/verified
`9883069b826bc1fcedbc99fe781ee41b54196d4f`; hosted rerun ended with overall failure and a cancelled job containing no steps; GitHub annotation reports no hosted runner acquired after repeated attempts.
The new-tool bundle remains
unaccepted until root records integrated results/publication.

Additional physical-timing finding: source-to-denoised click times shifted about
25 ms on three synthetic fixtures, with source 20 ms-threshold recall 1 and
processed recall 0. Strong 32 Hz content was preserved. Container/picture timing
checks remain valid; they do not prove unchanged waveform alignment.
Executable/profile-bound calibration and 1102-sample compensation have now been
used for the new actual run. Three standard-library and three optional synthetic
cases show zero candidate shift/click recall 1. This is processing-chain fixture
evidence; real-performance ground-truth alignment is not measured.

Current operator declaration 178 BPM is `operator_declared_not_audio_verified`.
The direct seed fit abstained; the new-run audio-periodicity fallback is
88.80090652730368 BPM with limited heuristic evidence and approximately 177.6018
double interpretation. Earlier 88.800719/177.6014 values belong to the first run.
Selection: `audio_periodicity_fallback_after_declared_seed_fit_abstention`.
This is not verified metronome identity or an exact 178 BPM acceptance claim.

Current flag breakdown: 112 four-pulse navigation proxies, 45 texture regions,
11 recurrence regions, 6 attack-density differences, 3 low-register riff/breakdown
candidates, 9 motif-timing differences; total 186. These are hypotheses, not
confirmed errors. Four-pulse proxies do not establish meter/bars, and 48 regions
do not establish semantic phrases. Tonic/mode and definite errors remain unknown.

Root's first-publication broadcast released the existing-file freeze for each
named owner. Ownership still applies; shared mutations/publication remain root's
responsibility. New-lane test results are worker handoffs pending root integration,
not proof that the published source contains those tools.

Latest root checkpoint: nineteen-tool integration passed 219/219 tests in 160.966 s,
recorded in `artifacts/nineteen-tool-release-tests.log` (writer independently read
its final OK). Current calibrated run `20261005T211103Z-c6d0bac2fcd2` now has
verified final decoded AAC −18.07 LUFS/−1.56 dBTP after −0.06 dB encoder feed.
Master measured −18.01/−1.50. The earlier −1.49 encoded failure is preserved
historical evidence and has been repaired by bounded retry. Listening is pending.
Wave2 source publication is pending root; main 9883069 / CI 37373960394 were last
reported queued/unverified in the preceding snapshot. Live root readback at21:51UTC shows overall failure with a cancelled job containing no steps, so no hosted test result exists for this revision.
Discovery remains 48 regions, 14 recurrence pairs and 186 review/navigation flags,
all hypotheses. Sparse pitch covers 20 sampled seconds including the ending;
meter and tonic/mode remain unknown. These are not whole-take note grading.

Linear: TIN-5485 In Review, listening pending; publication comment
`9d2e2ef7-6b74-49b3-972c-d75bd2884804`. TIN-5495 In Progress; goal comment
`353d44f7-02e8-4706-83d7-8b3e61232060`. The horizon remains October 6,
06:49:34 UTC. First publication does not end or complete the goal.

New meter/tonal/AU-automation lanes share this horizon and the following-week
allocation. They add no duplicate weekly hours. Their locally tested source/contracts
remain unpublished until root records integrated publication.

Checkpoint updates are short factual rows. Mark unknown/hold and next resolving
action. Never promote queued work, source checks, generic markers or rendered
media into host/application acceptance.
