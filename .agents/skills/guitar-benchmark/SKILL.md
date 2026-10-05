---
name: guitar-benchmark
description: Generate or run bounded synthetic technical-guitar benchmarks to measure preservation, noise and event-detection behavior; do not treat synthetic scores as acceptance of a real recording.
---

# Measure synthetic guitar-tool behavior

**Hook:** MCP tool `benchmark` and MCP prompt `guitar-benchmark`; inspect `tools/list` for publication status and supported arguments. The deterministic synthetic worker is implemented.

## Use and controls

Use `benchmark` with `output`, a new directory beneath this repository's `artifacts/benchmarks/`, and `operation` (`run` default or `fixtures`). `suite` selects `technical-v1` (default) or `technical-v2` for either operation. A run accepts `profile` (`bypass|conservative3|mild6`, default `conservative3`) and `phrase_backend` (`stdlib|librosa`, default `stdlib`). Those controls do not apply to fixtures-only generation. Optional librosa requires the existing locked analysis environment; no call installs dependencies.

Recipe: `just tool-run benchmark '{"output":"<repo>/artifacts/benchmarks/<new-name>","operation":"run","suite":"technical-v2"}'`. Direct workers are `python3 scripts/benchmark.py fixtures --output "<new-directory>" [--suite technical-v2]` and `python3 scripts/benchmark.py run --output "<new-directory>" --profile conservative3 --phrase-backend stdlib [--suite technical-v2]`.

Read [the original benchmark contract](../../../docs/spec/BENCHMARK_LANE.md), [the generated calibration bank contract](../../../docs/spec/BENCHMARK_CALIBRATION_LANE.md), and `program/benchmarks.json` / `program/benchmarks-v2.json`. Suite `technical-v1` creates three deterministic eight-second 48 kHz mono cases. `technical-v2` preserves those examples and adds nine cases, twelve cases/120 seconds total. It includes the exact custom nine-string registry ladder, missing synthesized C1 fundamental, legato, sweep/polyphony, rests/tuplets, variable tempo, click overlap and injected timing edits. The 32.000 Hz preservation sentinel remains distinct from theoretical C1 at approximately 32.703 Hz.

Generated clean/click/noise/mixture references carry native sample origin, extent and byte hashes. These are known generator components, not recovered phone-recording stems. Fixed seeds and sample-quantized event truth are not musician intent. Workers run serially with 120-second worker and 600-second suite limits; v2 caps each case at twelve seconds and uses at most two numerical threads. The runner never acquires private recordings, uses the network, downloads models or compiles tools.

## Evidence and acceptance

Inspect the nested worker result and `benchmark.json`; successful tool dispatch alone does not mean the suite passed. Results distinguish fixture creation, completed synthetic measurements and failure. Check component/source/configuration/lock/tool hashes, PCM extent and input immutability first, then coherent low-frequency gain, quiet-region change, gain-adjusted clean-reference error, click-time precision/recall and phrase overlap. Unavailable/rejected metric schemas are findings, not passes.

Keep a 32 Hz preservation sentinel separate from psychoacoustic acceptance. Distorted palm mutes, legato and coincident click/guitar attacks reveal different failure modes. A gain-only level change is not noise removal; synthetic event labels are generated truth, not confirmed identities in the phone take. Timing bias, false positives and missing phrase proposals should stay visible instead of being hidden in an aggregate score.

Changing the algorithm, dependency/tool revision, fixture set or scoring tolerance requires a new recorded comparison. Never change known truth or silently subtract measured latency to improve a score. Research metric choices in primary documentation and retain the task and tolerance they measure.

Fixture generation and restoration/analysis measurements are separate from the `pitch_evaluate` and `phrase_evaluate` hooks. Evaluators consume existing hash-bound pilot receipts; invoking `benchmark` alone does not establish that either calibration task ran. Inspect each task's actual coverage, exclusions, unavailable backend and deadline status before reporting completion. Generated labels must never enter discovery or DTW as a reference, and absent candidates against applicable positive truth remain missed detections rather than expected abstentions.

V2 discovery is unseeded: the bank's generated BPM and score do not become discovery inputs or truth-derived click templates. Its click stage is detection only. Pitch/expanded phrase calibration remain `not_requested` in benchmark-run receipts, and attenuation safety is `not_evaluated` when no attenuation ran. No case selector or automatic pilot-execution knob is exposed. Preserve the source/extent/32 Hz and exact denoised-bypass gates separately from these unrequested tasks.

**Review scenario:** A deliberately damaging high-pass should trigger low-frequency evidence even if the output is quieter. A louder bypass should not earn noise-reduction credit. Duplicate click candidates must not satisfy one truth event twice.

## Agent iteration

Choose the task-specific fixture and metric, compare a bounded setting change against bypass/previous evidence in fresh output directories, inspect structural failures and quality alerts, then save source/tool/settings hashes and limitations. Follow [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for provenance and receipts. Synthetic checks, actual-take measurements, operator listening, native editor import and AU/Logic proof remain separate states.
