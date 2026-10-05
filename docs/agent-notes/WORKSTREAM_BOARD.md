# video-utils parallel work board

As-of factual snapshot: October 5, 2026, approximately 20:57 UTC / 4:57 p.m.
America/New_York. Root's observed goal start is 20:49:34 UTC; the planned ten-hour
end is October 6, 06:49:34 UTC / 2:49:34 a.m. EDT. The active goal's objective/status
mechanism does not itself enforce a time deadline. This is the repository-local board for the operator's
ten-hour goal; the global Lab board remains under its own authority. Root owns
integrated status and must refresh this snapshot from live worker handoffs.

Authority: operator-approved parallel implementation and ten-hour goal;
R-HOOK-CONVERGENCE-20261004 / R-N11/R-N12/R-N13, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`.

Plan and ownership: [TEN_HOUR_PLAN.md](../spec/TEN_HOUR_PLAN.md).
Prompt record: [2026-10-05-user-prompts.md](2026-10-05-user-prompts.md).
Project/issue identities: [linear.json](../../program/linear.json).
Active goal issue: [TIN-5495 — ten-hour parallel implementation](https://linear.app/tinyland/issue/TIN-5495/ten-hour-parallel-guitar-toolkit-implementation-goal).

| Stream | Owner | Repo / branch | State / evidence | Next |
| --- | --- | --- | --- | --- |
| Integration/publication | `/root` | `video-utils` / `main` | Initial signed local commit exists; private remote, Linear project and TIN-5495 created; 108-test integrated suite passed including integer overflow/fallback; strict-JSON follow-up targeted27tests passed; push state must be read back | Publish tested first-release files/plans; future new-code acceptance stays separate |
| Cleaned demo | `/root` | `video-utils` / `main` | Run `20261005T203619Z-f94eb8eb2a1a` completed; measured −18.00 LUFS / −1.50 dBTP master; listening unreviewed | Preserve baseline evidence; compare new analysis without inventing listening acceptance |
| Rhythm/tempo/clicks | `/root/rhythm_analysis` | `video-utils` / `main` | Actual fallback fit verified at 88.800719 BPM; double interpretation 177.6014; approximate operator 178 kept separately; direct 178-seed fit abstained | Retain heuristic confidence/metronome uncertainty; next click candidates and attack-preservation comparison |
| Automatic guitar features/pitch | `/root/guitar_features` | `video-utils` / `main` | Actual post-denoise librosa pass: 47 segment candidates, 10 recurrence pairs, 112 four-pulse proxies, 57 proposed review spans; tuning context regenerated in noise/tone/notes/phrases | Integrate candidates as hypotheses; next `scripts/pitch.py`, `tests/test_pitch.py`, PITCH_LANE; no intended-note verdict without reference |
| Phrase DAG/comparison | `/root/phrase_dag` | `video-utils` / `main` | DAG/markers/report rerun: 177 source-time review/navigation flags; all discovery or difference hypotheses, no confirmed errors | Next recurrence-difference worker and tests; native editor import remains separate |
| Typed tool extensions | `/root/tool_hooks` | `video-utils` / `main` | Twelve hooks; oversized JSON integer `10**400` overflow handling fixed with regression test; 108-test integrated suite and27-test targeted strict-JSON suite passed | Next MCP_EXTENSION_LANE/contract tests; existing registry edits after root first-push broadcast |
| Tool skill extensions | `/root/tool_skills` | `video-utils` / `main` | Twelve skills; next SKILL_EXTENSION_LANE | Extend per-tool skills after validated contract handoff |
| Graphical evidence review | `/root/plan_review` | `video-utils` / `main` | Local report foundation; next `review_server.py`, tests, REVIEW_LANE and `staticreview/**` | Local source-time graphical review with path/resource safeguards |
| Research/spec/docs | `/root/clip_baseline` | `video-utils` / `main` | Docs/tuning handoff complete; standby | Further research only after explicit assignment; root appends observed integration facts |
| Benchmark/annotation | `/root/repo_patterns` | `video-utils` / `main` | Tooling handoff complete; assigned `benchmark.py`, tests, benchmarks.json and BENCHMARK_LANE | Bounded reproducible fixtures/results and exact provenance |
| Native AU architecture spike | `/root/au_architecture` | `video-utils` / `main` | CLI/DSP handoff complete; assigned `native/au-spike/**` and AU_SPIKE | ABI/render constraints and bounded spike tests; actual Logic acceptance remains unknown |
| Durable goal/prompts | `/root/goal_plan` | `video-utils` / `main` | Owned prompt archive, exact horizon, assignment plan and this board written | Root integrates/publishes and refreshes live lane facts |
| Additional lanes | Unassigned | `video-utils` / isolated named files required | No further assignment claim | Root records exact owner, files, acceptance and dependencies before delegation |
| Listening/AU/editor acceptance | Operator / future named lane | Local run / future host | Listening pending; AU/Logic and native FCP/Resolve import unverified | Audition current media; separately plan actual host/application acceptance |

The initial 81 Python tests and seven Rust tests passed before these active
automatic-discovery/tuning enhancements. A later 108-test Python suite passed including integer-overflow and tempo-fallback
regressions. The subsequent strict-JSON parser fixes passed27targeted tool/MCP
checks. Root records these against the source/publication receipt; future new
worker tests and host/application acceptance remain separate.

Observed current analysis: operator declaration 178 BPM is marked
`operator_declared_not_audio_verified`. The direct 178-seed fit abstained, and
the audio-periodicity fallback now fits 88.80071920784458 BPM with limited
heuristic evidence; its double-time interpretation is approximately 177.6014.
Selection is `audio_periodicity_fallback_after_declared_seed_fit_abstention`.
This is not verified metronome identity or confirmation of an exact 178 grid.

Observed regenerated flag breakdown: 112 four-pulse navigation proxies, 43
spectral-texture regions, 9 recurrence regions, 6 attack-density differences,
4 low-register riff/breakdown candidates, and 3 motif-timing differences,
total 177. Navigation and texture flags are not performance errors. Four-pulse
proxies do not establish meter or musical bars, and the 47 segmented regions do
not establish semantic phrases. Tonic/mode and definite performance errors remain
unknown. Root must refresh facts after any additional rerun.

Publication freeze: existing shared files remain frozen until root broadcasts
the first integrated publication. Newly assigned isolated files may proceed.
The board records assignments, not proof that each worker is executing them or
that its acceptance checks have passed.

Checkpoint updates should be short factual rows. State blockers as unknown/hold
with the next resolving action. Do not advertise queued work, source-only checks,
generic marker export, or rendered media as live host acceptance.
