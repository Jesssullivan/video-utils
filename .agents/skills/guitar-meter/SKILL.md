---
name: guitar-meter
description: Rank automatic pulse-accent cycle hypotheses from hash-bound guitar analysis while separating metrical notation, downbeats and tuplets from uncertain energy evidence.
---

# Inspect pulse accents and meter hypotheses

**Hook:** MCP tool `meter` and MCP prompt `guitar-meter`; inspect `tools/list` for publication status. The bounded offline worker is implemented. Its only analysis input is `run_dir`; algorithm thresholds are fixed and recorded, not exposed knobs.

## Use and evidence

Use `meter` with a run directory and the supported tool timeout. Recipe fallback after registry publication: `just tool-run meter '{"run_dir":"<run-dir>"}'`. Direct worker: `python3 scripts/meter.py --run-dir "<run-dir>"`.

Read [the meter contract](../../../docs/spec/METER_LANE.md) and [primary research](../../../docs/research/METER.md). The worker reads existing `manifest.json` and hash-bound `analysis.json`, checks restored-input/original-source lineage, source-time origin and no-stretch mapping, then writes a new immutable `meter/<timestamp>/meter.json`. It does not rewrite media, analysis, flags or reports or download a model.

Inspect fitted pulse and half/double aliases, repeated accent-cycle ranks, local-window consistency, explained variance, threshold/bound evidence and unknown reasons. Missing existing MFCC features/grid yields explicit unknown, not an invented meter. Pulse selection/feature extraction are upstream evidence; this worker does not expose a tempo override or run a learned downbeat model.

## Nine-string interpretation

Automatic accent discovery needs no intended score. A 3/4/7-pulse cycle is an accent hypothesis, not automatically 3/4, 4/4 or 7/8 notation. Candidate notation assumes quarter/eighth pulse units; those units, true downbeats and additive groupings are not inferred. Uniform clicks establish periodic pulse but cannot determine beats per bar. Seven equal subdivisions over four pulses can resemble a seven-unit pattern without proving 7/8.

MFCC energy contains clicks and distorted guitar together. Compression, palm mutes, legato, tapping and sweeps can hide or create accents. Preserve near-32 Hz guitar context and do not filter low content to manufacture strong accents. Local conflicts, uniform patterns and insufficient repeats should abstain; unknown does not mean the performance lacks a meter.

Confidence is heuristic. Keep operator-declared tempo distinct from observed fitted pulse and aliases; a confirmed BPM does not settle meter. Do not lower fixed thresholds merely to force a time-signature label or use an accent-cycle result to grade missed/extra notes.

**Review scenario:** Uniform metronome clicks or sustained legato should remain unknown. Repeatable synthetic triple accents can support a three-pulse cycle, while notated unit/downbeat remain separate. A real take with very weak energy-proxy evidence should preserve that abstention.

## Agent iteration

Inspect input/lineage and accent evidence, compare supported upstream analyses or existing local windows, and identify which missing evidence would distinguish candidate cycles. Research metrical/downbeat methods in the linked primary sources before proposing a new worker/control. Record settings, source/artifact hashes, aliases, uncertainty and actual listening status through [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md). Synthetic meter checks and musical interpretation of the take remain separate evidence.
