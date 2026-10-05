---
name: guitar-benchmark
description: Generate or run bounded synthetic technical-guitar benchmarks to measure preservation, noise and event-detection behavior; do not treat synthetic scores as acceptance of a real recording.
---

# Measure synthetic guitar-tool behavior

**Hook:** MCP tool `benchmark` and MCP prompt `guitar-benchmark`; inspect `tools/list` for publication status and supported arguments. The deterministic synthetic worker is implemented.

## Use and controls

Use `benchmark` with `output`, a new directory beneath this repository's `artifacts/benchmarks/`, and `operation` (`run` default or `fixtures`). A run accepts `profile` (`bypass|conservative3|mild6`, default `conservative3`) and `phrase_backend` (`stdlib|librosa`, default `stdlib`). Those controls do not apply to fixtures-only generation. Optional librosa requires the existing locked analysis environment; no call installs dependencies.

Recipe fallback after registry publication: `just tool-run benchmark '{"output":"<repo>/artifacts/benchmarks/<new-name>","operation":"run"}'`. Direct workers are `python3 scripts/benchmark.py fixtures --output "<new-directory>"` and `python3 scripts/benchmark.py run --output "<new-directory>" --profile conservative3 --phrase-backend stdlib`.

Read [the benchmark contract](../../../docs/spec/BENCHMARK_LANE.md) and `program/benchmarks.json`. Suite `technical-v1` creates three deterministic eight-second 48 kHz mono cases with known component/region truth. Workers run serially with 120-second worker and 600-second suite limits. It never acquires private recordings, uses the network, downloads models or compiles tools.

## Evidence and acceptance

Inspect the nested worker result and `benchmark.json`; successful tool dispatch alone does not mean the suite passed. Results distinguish fixture creation, completed synthetic measurements and failure. Check component/source/configuration/lock/tool hashes, PCM extent and input immutability first, then coherent low-frequency gain, quiet-region change, gain-adjusted clean-reference error, click-time precision/recall and phrase overlap. Unavailable/rejected metric schemas are findings, not passes.

Keep a 32 Hz preservation sentinel separate from psychoacoustic acceptance. Distorted palm mutes, legato and coincident click/guitar attacks reveal different failure modes. A gain-only level change is not noise removal; synthetic event labels are generated truth, not confirmed identities in the phone take. Timing bias, false positives and missing phrase proposals should stay visible instead of being hidden in an aggregate score.

Changing the algorithm, dependency/tool revision, fixture set or scoring tolerance requires a new recorded comparison. Never change known truth or silently subtract measured latency to improve a score. Research metric choices in primary documentation and retain the task and tolerance they measure.

**Review scenario:** A deliberately damaging high-pass should trigger low-frequency evidence even if the output is quieter. A louder bypass should not earn noise-reduction credit. Duplicate click candidates must not satisfy one truth event twice.

## Agent iteration

Choose the task-specific fixture and metric, compare a bounded setting change against bypass/previous evidence in fresh output directories, inspect structural failures and quality alerts, then save source/tool/settings hashes and limitations. Follow [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for provenance and receipts. Synthetic checks, actual-take measurements, operator listening, native editor import and AU/Logic proof remain separate states.
