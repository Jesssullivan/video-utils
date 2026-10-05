# video-utils parallel work board

As-of publication/assignment snapshot: **2026-10-05 21:54:58 UTC / 5:54:58 p.m. EDT**.
Root's goal began 20:49:34 UTC and remains **active**, with planned end
**2026-10-06 06:49:34 UTC / 2:49:34 a.m. EDT**. The objective/status tool does
not enforce a wall-clock deadline. This board does not replace the global Lab
board. Root owns integration, factual tracker updates and publication.

Authority: operator parallel implementation/ten-hour goal; repository AGENTS.md;
R-HOOK-CONVERGENCE-20261004 / R-N11/R-N12/R-N13, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`.

Plan: [TEN_HOUR_PLAN.md](../spec/TEN_HOUR_PLAN.md).
Prompts: [2026-10-05-user-prompts.md](2026-10-05-user-prompts.md).
Checkpoints: [2026-10-05-goal-checkpoints.md](2026-10-05-goal-checkpoints.md).
Current continuation contract: [GRAPH_INTEGRATION_LANE.md](../spec/GRAPH_INTEGRATION_LANE.md).
Project IDs: [linear.json](../../program/linear.json).
Active goal: [TIN-5495](https://linear.app/tinyland/issue/TIN-5495/ten-hour-parallel-guitar-toolkit-implementation-goal).

Published baseline: **signed/private/verified** source
`6f7d1965b3c99a9b2ed261d58ea8949c0d6a1b26` at
[Jesssullivan/video-utils](https://github.com/Jesssullivan/video-utils).
Nineteen hooks and nineteen skills are published. Local integration passed
**219/219 tests in 160.966 s**. Hosted CI
[37378799943](https://github.com/Jesssullivan/video-utils/actions/runs/37378799943)
**succeeded at 21:54:10 UTC**, including Python/media, Rust and secret scan jobs.
Hosted Python discovered 219 tests: 198 passed, 21 optional-backend skips in 18.903 s;
seven Rust tests and secret scan passed. Local analysis ran all 219 without skips.
These are source/hosted checks, not listening, AU hosting or editor-import proof.

## Six assigned continuation lanes

Only these six workers have active continuation assignments at this snapshot.
Earlier workers completed their handoffs and are not active by default. The
root integration lane continues; this documentation lane freezes after handoff.

| Stream | Owner | Exclusive files | State / evidence | Next / dependency |
| --- | --- | --- | --- | --- |
| Feature graph | `/root/phrase_dag` | `scripts/dag.py`, `tests/test_dag.py`, `docs/spec/GRAPH_FEATURES.md` | Assigned continuation; nineteen-tool baseline published | Publish bounded artifact selector contract first; verify source/upstream/settings hashes, staleness/symlinks, nulls and sparse coverage |
| Evidence report | `/root/plan_review` | `scripts/report.py`, `tests/test_report.py`, `docs/spec/REPORT_FEATURES.md` | Assigned continuation; prior real browser/synthetic annotation checks qualified | Depends on graph selector; display only graph-verified evidence, unknowns/sparse coverage; no new processing or guessed ground truth |
| Hook/skill graph interface | `/root/tool_hooks` | `program/tools.json`, `scripts/tool_api.py`, `tests/test_tool_contracts.py`, `docs/spec/GRAPH_TOOL_CONTRACT.md`, `.agents/skills/guitar-pipeline/SKILL.md` | Assigned continuation; nineteen published hooks/skills | Depends on graph selector; expose bounded optional evidence inputs through existing DAG tool, retain nineteen-tool count and exact skill readback |
| Corpus annotation | `/root/repo_patterns` | `scripts/corpus.py`, `tests/test_corpus.py`, `docs/spec/CORPUS_LANE.md` | New bounded local-manifest assignment | Explicit labelled spans/reviewer provenance; distinguish fixture labels from musician truth; no downloads; no audio-tool claim before API/skill integration |
| Editor-marker research | `/root/clip_baseline` | `docs/research/EDITOR_MARKERS.md`, `docs/spec/EDITOR_MARKER_SPIKE.md` | Assigned source-only format/design continuation | Current primary FCPXML/Resolve semantics, VFR/offsets/sample-frame rounding; fixtures do not establish application import compatibility |
| Native parameter state | `/root/au_architecture` | `native/au-spike/state/**`, `docs/spec/AU_STATE.md` | Assigned isolated experiment; existing native/automation files frozen | Bounded state validation/serialization and restore-before-render; no registration, host configuration or device operation |

Root alone integrates, reruns relevant checks and the calibrated demo, publishes
signed source and tracker facts. Assignment is not a completed implementation or
verified result. New corpus/development utilities are not audio-processing tools
until explicitly integrated with an API and skill. All continuation work shares
the existing horizon and weekly budgets; no duplicate hours are added.

## Delivered evidence and remaining acceptance

| Stream | Owner / state | Evidence | Remaining boundary |
| --- | --- | --- | --- |
| Calibrated demo/export | Root; delivered numerically, listening pending | Run `20261005T211103Z-c6d0bac2fcd2`; master −18.01 LUFS/−1.50 dBTP; decoded AAC −18.07/−1.56 after −0.06 dB feed; bounded retry and 1102-sample compensation recorded | Listening and real-performance ground-truth alignment remain unmeasured; preserve earlier failed −1.49 export history |
| Noise/tempo/click/pitch | Earlier owners handed off; no new assignment by default | Operator 178 separate from fallback 88.800907/double177.6018; sparse pitch sampled 20 seconds including ending | Metronome identity/intended notes unknown; sparse analysis is not whole-take transcription |
| Meter/tonal | `/root/meter_inference`, `/root/tonal_inference`; handoffs done | Published nullable candidate workers and tests | Actual meter, tonic/mode remain unknown; no definitive correctness claim |
| Phrase/markers | Published baseline; DAG continuation above | 48 regions, 14 recurrence pairs, 186 review/navigation flags | Hypotheses rather than confirmed mistakes or semantic phrase/meter truth; native editor import unverified |
| Benchmark/browser review | Published baseline; owners reassigned above | Three stdlib+three optional synthetic cases: zero shift/click recall 1, optional phrase IoU 0.935; real muted browser playback/filter/decode and synthetic annotation edit/refresh passed | Synthetic scores do not establish real sound quality; no dummy real-take annotations; listening pending |
| Native spike/automation | Published qualified source/audit; owner reassigned to state only | Compiled/ARC audit and native recipe checks passed | No plugin installation, auval or Logic proof; existing files frozen during isolated state work |
| Independent review and tool skills | Prior handoffs done; no active default assignment | Earlier release review, validated skills/contracts | Additional review requires explicit assignment; root records new continuation acceptance |

Historical CI findings: run 37373112479 failed one excessive-nesting test.
Parser repair 9883069 subsequently passed local tests. Its hosted run
[37373960394](https://github.com/Jesssullivan/video-utils/actions/runs/37373960394)
ended with overall failure and no job steps; exact annotation:
“job was not acquired by Runner of type hosted even after multiple attempts”.
That revision has no hosted test result. The later published 6f7d196 run succeeded
as recorded above; do not reinterpret the runner failure as a source-test failure.

Linear: D0 TIN-5485 remains **In Review**, listening pending; wave2 comment
`6b0c27ce-950d-4f6a-a492-2cd6e821e567`. Goal TIN-5495 remains **In Progress**;
comment `18776874-b339-416f-a144-69a746ffdc9e`. IDs are synchronized by root in
program/linear.json. The goal is not completed by publication or hosted CI.

Root's initial publication freeze was released for named owners; current
continuation ownership replaces generic activity assumptions. Dirty shared work
and ignored media are preserved. Process signalling requires actual ownership/
live-session checks and R-N11 receipts; hooks remain advisory under R-N12;
durable facts and tracker receipts follow R-N13.
