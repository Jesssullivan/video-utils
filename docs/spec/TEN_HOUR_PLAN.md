# Ten-hour implementation horizon

Operator request, October 5, 2026: retain today's prompts and plan durably and
run a ten-hour goal with many parallel subagents. The root agent owns the active
goal and integration. This document specifies a planned work horizon; it does
not claim that the goal tool enforces a wall-clock budget or that ten hours have
already elapsed.

Root-observed goal creation timestamp `1791233374` establishes the planned
horizon: **2026-10-05 20:49:34 UTC → 2026-10-06 06:49:34 UTC**, equivalently
**October 5, 4:49:34 p.m. → October 6, 2:49:34 a.m. America/New_York (EDT)**.
The initial approximately 20:53 estimate is superseded by that observed creation
receipt. The goal is active at this plan's publication checkpoint. Ten hours is
a time horizon, not a token-budget request; the goal tool supports an objective
and status rather than an enforced wall-clock deadline.

The authoritative project scope and following week's allocations are in
[PROJECT.md](PROJECT.md). The operator's words are in
[2026-10-05-user-prompts.md](../agent-notes/2026-10-05-user-prompts.md).
The current lane board is
[WORKSTREAM_BOARD.md](../agent-notes/WORKSTREAM_BOARD.md).

## Reasserted outcome

Build a private, reproducible, local-first guitar-video toolkit around `just`,
Rust orchestration/DSP, FFmpeg restoration/export, bounded Python analysis, and
R/Quarto research reporting. Nix and committed locks define environments.
Preserve the original recording, low-frequency musical content, source rate,
channels, and original timeline. Produce a cleaned WAV and synchronized video
that can be auditioned against source/bypass, plus evidence explaining each
operation. Keep numerical checks and listening acceptance separate.

The instrument is a nine-string deathcore/technical guitar with constant tuning
pitch classes **C F B♭ E♭ B♭ E♭ A♭ C F**, lowest to highest. Inferred octaves
are **C1 F1 B♭1 E♭2 B♭2 E♭3 A♭3 C4 F4** at A4=440 Hz; the lowest C1 is
approximately 32.703 Hz and highest F4 approximately 349.228 Hz. Preserve the
operator's supplied E♭2→B♭2 interval instead of silently normalizing to fourths.
See [instrument.json](../../program/instrument.json) and linked primary sources
in the README for frequency evidence. Tuning metadata is not pitch detection.

Analysis follows a hash-bound graph: **denoise → click/BPM → nullable
pitch/tonic/mode and repeated-phrase evidence → recurrence comparison → source
timestamp/span review flags**. Every operation has a typed MCP interface and a
repository skill so agents can inspect intents, research alternatives, compare
bounded knobs, and retain receipts. Discovery of phrases, bar groupings,
breakdowns, and recurring riffs works without a predefined intended arrangement.
References qualify definite correctness grading; recurrence differences remain
audition hypotheses when intent is unknown.

Keep the user's approximately **178 BPM** context separate from the previous
**177.6 BPM** double-time interpretation of fitted periodicity. Subdivisions,
rests, palm mutes, syncopation, tuplets, sweep picking, tapping and legato make
onset count unreliable as a note count. Do not label sparse attacks as missing
notes. A four-pulse grouping is a hypothesis, not confirmed meter.

## Definition of done for this horizon

1. A reproducible source-to-cleaned-WAV/video demo passes sample/timeline,
   source-immutability, loudness/peak, and low-frequency-preservation checks.
   Restore conservatively; no blanket 80 Hz high-pass, mains notch, speech
   denoiser or automatic click removal by default.
2. The actual take has source-time rhythm and automatic phrase/recurrence
   candidates with confidence and limitations. The report exposes review spans
   with local playback/seek controls. Empty or unknown results remain permitted
   when evidence is insufficient; populate candidates only from measured data.
3. All registered tool contracts and skills agree with supported knobs, input
   schemas, dependencies, timeouts and provenance. Optional analysis dependencies
   are reproducible and explicit; no silent model downloads.
4. Relevant synthetic/integration tests and an actual-take run substantiate
   behavior, including 32 Hz protection, distorted/legato ambiguity, source
   identity, recurrence differences and tool failures. Record exact results and
   distinguish optional-backend runtime evidence from source-only checks.
5. Root publishes signed source commits to the private repository, synchronizes
   the dedicated Linear project/issue facts, and leaves a durable handoff with
   exact completed work, unknowns, artifacts, checkpoints, and next actions.
6. The following week's 35-hour core and optional 35-hour extension retain clear
   acceptance tests and prioritization. Native AU/Logic and Final Cut/Resolve
   imports are separate milestones requiring actual host/application proof.

The current completed demo receipt is
[2026-10-05-implementation.md](../agent-notes/2026-10-05-implementation.md).
Its local run `artifacts/runs/20261005T203619Z-f94eb8eb2a1a` contains unreviewed
media. The initial standard-library phrase pass abstained and is preserved under
`analysis-revisions/stdlib-initial`. A later actual post-denoise librosa pass
produced 47 candidate regions, 10 recurrence pairs, 112 four-pulse proxies and 57
proposed review spans without predefined intent. These are discovery hypotheses,
not semantic phrase/meter correctness or performance grades. The current declared
178 BPM seed abstained; the verified audio-periodicity fallback fits 88.800719 BPM
(approximately 177.6014 at double time), with the approximate operator declaration
kept separate. The regenerated DAG/markers/report contains 177 source-time
navigation/review flags, all hypotheses rather than confirmed mistakes. See the
live board for counts and remaining test/publication evidence. Goal tracking is
[TIN-5495](https://linear.app/tinyland/issue/TIN-5495/ten-hour-parallel-guitar-toolkit-implementation-goal).

Later benchmark evidence found approximately 25 ms source-to-denoised click
delay in three synthetic fixtures. Executable/profile-bound calibration and
1102-sample compensation were then used in new run
`20261005T211103Z-c6d0bac2fcd2`; three standard-library and three optional-backend
synthetic cases now show zero candidate shift and click recall 1. This qualifies
the tested processing chain, not a ground-truth alignment of the real performance.
The new run completed all stages with 48 candidate regions, 14 recurrence pairs
and 186 review/navigation flags. Its encoded AAC true peak measured −1.49 dBTP,
failing the strict −1.50 target; bounded headroom retry repair is in progress.
Root has not published the new bundle. `/root/media_latency` owns media/latency
tests and `docs/spec/MEDIA_LATENCY.md`; definition-of-done item 1 remains open
until final encoded acceptance and publication evidence are recorded.

## Parallel lanes and ownership

Workers edit their assigned files only. Root resolves interface changes and owns
shared entrypoints, publication, Linear writes, and integrated run receipts.
The initial existing-file freeze **was released by root's first-publication
broadcast** after signed commit `be085b4316c27ba59d66091a01480493ed9c996d` was
pushed and verified. Named owners may resume their assigned files; root still
coordinates shared interfaces and publication. These tables retain the assignment
contract; the live board records current evidence and remaining acceptance.
Publishing the first iteration does not complete the ten-hour goal.

| Lane | Owned files | Deliverable and verification | Dependency / checkpoint |
| --- | --- | --- | --- |
| `/root/rhythm_analysis` | `scripts/rhythm.py`, `tests/test_rhythm.py`, `requirements-analysis.*` | Declared versus fitted tempo, bounded optional onset backend, subdivision ambiguity; known-grid and real-take checks | Agree schema with features/tools/report before integration |
| `/root/guitar_features` | `scripts/guitar_features.py`, `tests/test_guitar_features.py`, `docs/research/LOW_TUNING.md` | Beat-synchronous novelty/self-similarity/recurrence candidates without intent; low-register and legato fixtures | Uses post-denoise identity and tempo context; publish schema to DAG/report |
| `/root/phrase_dag` | `scripts/dag.py`, `scripts/markers.py`, `program/dags/guitar-take.json`, `tests/test_dag.py`, `tests/test_markers.py`, `docs/spec/PHRASE_DAG.md` | Provenance evaluator, automatic review spans, optional qualified-reference comparator, generic markers | Feature artifact schema first; no native editor-import claim |
| `/root/tool_hooks` | `scripts/tool_api.py`, `scripts/mcp_server.py`, `program/tools.json`, `tests/test_tools.py`, `tests/test_mcp.py`, `docs/spec/MCP.md` | Typed interfaces for all registered tools, validated knobs, bounded workers and explicit backend selection | Coordinate worker arguments and skills; actual stdio checks |
| `/root/tool_skills` | `.agents/skills/**`, `docs/spec/AGENT_TOOLS.md` | Tool intent/research/iteration instructions matching actual contracts | Contracts first, validator plus live prompt reads |
| `/root/plan_review` | `scripts/report.py`, `reports/demo.qmd`, `reports/plots.R`, `tests/test_report.py` | Evidence report, declared/fitted tempo, candidate spans/recurrence seeks, stale-artifact rejection | Feature/DAG schemas; no invented browser or Quarto runtime proof |
| `/root/clip_baseline` | `README.md`, `docs/spec/PROJECT.md`, `docs/research/RESEARCH.md`, `docs/agent-notes/2026-10-05-implementation.md`, `program/models.json` | Domain/acceptance/research documentation and current roadmap; preserve observed receipts | Root supplies actual integrated measurements/publication |
| `/root/repo_patterns` | `flake.nix`, `flake.lock`, `justfile`, `just/*.just`, `.github/**`, `.gitignore`, `pyproject.toml`, `uv.lock`, environment/doctor/model-prefetch support | Pinned lightweight environment and operator recipes; source/runtime evidence separated | Existing lane may be idle after completed handoff; root reassigns explicitly |
| `/root/au_architecture` | `src/**`, `Cargo.toml`, `Cargo.lock`, `rust-toolchain.toml`; assigned AU research notes | Dependency-free CLI/DSP checks and future ABI/real-time architecture | AU implementation only if root assigns bounded spike; no plugin installation |
| `/root/goal_plan` | `docs/spec/TEN_HOUR_PLAN.md`, `docs/agent-notes/2026-10-05-user-prompts.md`, `docs/agent-notes/WORKSTREAM_BOARD.md` | Durable operator requests, horizon, named lanes and checkpoint/handoff contract | Root supplies exact goal start and newly assigned lane names |
| Root integration | `AGENTS.md`, `scripts/run_demo.py`, other explicitly retained shared files, `program/linear.json`, final publication receipts | Integrate and test, rerun real media/analysis, commit/push, publish factual Linear updates | Root alone updates shared entrypoint/publication; no race with named owners |

The root has assigned the following next work to existing named agents, using
new files to avoid races with first-publication integration. References to
"after first push" below describe a dependency now satisfied; new contracts/tests
still require root integration before publication:

| Owner | New files / scope | Acceptance checkpoint |
| --- | --- | --- |
| `/root/rhythm_analysis` | `scripts/clicks.py`, `tests/test_clicks.py`, `docs/spec/CLICK_LANE.md`, `docs/research/CLICK_RESEARCH.md` | Measured click candidates and bounded attenuation experiment; overlapping guitar attacks protected; primary-source research |
| `/root/guitar_features` | `scripts/pitch.py`, `tests/test_pitch.py`, `docs/spec/PITCH_LANE.md` | Use constant tuning with inferred-octave evidence; bounded optional dual-resolution pitch candidates; low-register/intentional-distortion ambiguity and unknowns retained |
| `/root/meter_inference` | `scripts/meter.py`, `tests/test_meter.py`, `docs/spec/METER_LANE.md`, `docs/research/METER.md` | Confidence-qualified meter candidates without intended arrangement; ambiguous accents, subdivisions and half/double interpretations permit unknown |
| `/root/tonal_inference` | `scripts/tonal.py`, `tests/test_tonal.py`, `docs/spec/TONAL_LANE.md`, `docs/research/TONAL.md` | Distortion-aware tonic/mode candidates with primary-source methods, protected low register and abstention on insufficient evidence |
| `/root/phrase_dag` | `scripts/phrase_compare.py`, `tests/test_phrase_compare.py`, `docs/spec/PHRASE_COMPARE_LANE.md` | Reference-free recurrence-difference review with source spans; tests distinguish hypotheses from correctness |
| `/root/repo_patterns` | `scripts/benchmark.py`, `tests/test_benchmark.py`, `program/benchmarks.json`, `docs/spec/BENCHMARK_LANE.md` | Reproducible benchmark records with exact fixture/output provenance and bounded resources |
| `/root/plan_review` | `scripts/review_server.py`, `tests/test_review_server.py`, `docs/spec/REVIEW_LANE.md`, `staticreview/**` | Local graphical review and source-time navigation; resource/path boundaries and playback claims tested |
| `/root/au_architecture` | Initial `native/au-spike/**` and `docs/spec/AU_SPIKE.md` handoff; next only `native/au-spike/automation/**` and `docs/spec/AU_AUTOMATION.md` | Isolated automation experiments; existing native spike frozen until root publication; no installation or host-acceptance claim |
| `/root/tool_hooks` | `docs/spec/MCP_EXTENSION_LANE.md`, `tests/test_tool_contracts.py`; existing registry only after root's first-push broadcast | Extension contracts agree with supported operations and explicit dependencies before shared registry edits |
| `/root/tool_skills` | `docs/spec/SKILL_EXTENSION_LANE.md`; per-tool extensions after contract handoff | Agent guidance matches actual validated new tool contracts |
| `/root/clip_baseline` | `docs/research/FOSS_AUDIO_MATRIX.md`, `docs/spec/RESEARCH_LANE.md` | Primary-source FOSS applicability/licensing comparison for distorted low-register guitar; separate repairs research from host changes |

Assignment versus execution: the earlier publication broadcast did not trigger
the idle pitch worker. Root explicitly started `/root/guitar_features`'s pitch
follow-up around 21:20 UTC. Treat earlier pitch rows as assignments, not evidence
that pitch implementation was running before that follow-up.

Meter, tonal and AU automation assignments continue the existing ten-hour
horizon. They do not create extra hours beyond the project's 35-hour core plus
optional 35-hour following-week allocation. Root prioritizes bounded evidence and
unknowns; new workers/tools remain unpublished until their implementation,
contracts and relevant tests are integrated and verified.

Any additional lane remains unassigned until root records an exact owner and
isolated files. An idle lane does not authorize another agent to overwrite its
owned files. Scope changes require a board/ownership update, not an implicit
transfer inferred from Git activity.

## Checkpoints and dependency order

| Elapsed horizon | Required checkpoint | Root integration decision |
| --- | --- | --- |
| H+0 to H+1 | Durable prompts/plan, tuning evidence, named file ownership; actual cleaned demo preserved | Record start receipt and accepted baseline; choose bounded optional backend |
| H+1 to H+2 | Rhythm/features schema agreed; automatic candidate pilot on real take; interfaces forward supported knobs | Run source/hash/time alignment checks before interpreting candidates |
| H+2 to H+4 | DAG/report/skills consume new candidates; meaningful fixture tests; first independent review | Publish reviewable iteration and Linear facts; retain prior run evidence |
| H+4 to H+6 | Research-backed click/denoise comparisons or phrase benchmark refinements, if initial integration is stable | Promote only evaluated settings; record abstentions and failed experiments |
| H+6 to H+8 | Robustness, resource limits, interrupted-run behavior, reproducibility; marker/AU research spikes if assigned | Keep optional investigations separate from core acceptance |
| H+8 to H+10 | Final independent review, actual demo reproduction, source/private-remote evidence, roadmap/handoff | Integrate completed work, record all remaining unknowns and exact next tasks |

Checkpoints are work windows rather than forced sleeps. Root can rebalance idle
lanes after completed handoffs and communicate changed ownership before edits.
No worker runs an unrelated mutation while waiting on a schema dependency.

## Resource and evidence rules

- Bound local numerical threads and memory; use approved builders for heavy
  compilation and check cluster capacity before any GPU placement. No new daemon
  or heavyweight learned-model work is implied by the ten-hour request.
- Model registration requires exact artifact, license and expected hash; download
  is explicit. The current registry is empty. Source separation yields estimates
  from a mono mixture, not recovered original tracks.
- Retain source/output hashes, parameters, original timeline and analysis
  resampling provenance. A rerun preserves old measurements instead of silently
  replacing the only evidence copy.
- Research primary sources; cite licensing, intended use and applicability to
  distorted low-register guitar. Treat AU cleanup/repair research separately
  from any host/plugin mutation.
- R-N12 makes hooks advisory. Record findings and traceable alternatives in
  durable notes; do not invent approval gates.
- Under R-N11, signal only owned recorded tasks after actual target/live-session
  checks. Never infer ownership from a default tmux socket or terminate another
  session. Escape-hatch receipt format is
  `actor | target/ownership | reason | ruling | prior_state | result`.

## Horizon stop and resumable handoff

At H+10, root records the actual elapsed time and completion state. Do not mark
the active goal complete merely because its horizon elapsed: completion requires
the stated outcome. If work remains, retain the active goal with explicit
remaining tasks unless the operator requests a pause or another permitted status
condition applies. Root reports the bounded work performed and any unresolved
acceptance dependency without claiming additional unattended execution.

Workers finish or safely checkpoint their owned operations; they do not leave
anonymous background jobs. Record live owned processes and artifact locations.
Any signalling follows R-N11 inspection and receipts. Preserve dirty/shared
work and ignored media; do not reap other sessions or discard experiments.
Save the exact next action per lane, current Git state, tested commit/run IDs,
publication state, and unknowns in `docs/agent-notes/`; mirror factual tracker
evidence to Linear under R-N13. Listening, AU validation, Logic hosting, native
editor marker import and optional report-runtime acceptance remain separate.

Authority: operator's October 5 implementation, fanout and ten-hour goal requests;
repository `AGENTS.md`; R-HOOK-CONVERGENCE-20261004, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`; R-N11/R-N12/R-N13.
