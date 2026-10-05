---
name: guitar-phrases
description: Discover phrase, bar and breakdown candidates in technical guitar automatically, and mark recurrence differences for review without requiring a predefined intended phrase.
---

# Discover guitar phrases and mark self-consistency differences

**Hook:** MCP tool `phrases` and MCP prompt `guitar-phrases`. Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. Skill availability does not imply a server connection has been installed in this agent.

**Capability:** Experimental automatic phrase/recurrence discovery and source-timestamped review spans. Same-source BPM/notes context is attached when available. Candidate musical structure can be discovered without an intended-rhythm reference; definite correctness judgments remain separate.

## Use and controls

Use MCP `phrases`; fallback: `just tool-run phrases '{"input":"<input>","run_dir":"<run-dir>"}'`. The direct worker is `python3 scripts/guitar_features.py phrases "<input>" --run-dir "<run-dir>"`. Run discovery even when no intended phrase or score has been supplied. Use available beat-synchronous features and recurrence evidence to propose phrase/bar/breakdown boundaries, listen around suggestions, and distinguish a mute/rest from a structural change before confirming structure.

Current MCP controls are `backend` (`stdlib` default or optional `librosa`), `bpm` (20–400 pulse seed) and bounded `timeout_seconds`. Inspect `tools/list` before calls because schema and dependency qualification may change. Pass an operator-confirmed BPM when available, retaining its provenance; otherwise preserve tempo alternatives. The stdlib fallback uses energy pauses and envelope recurrence. The librosa backend compares beat-synchronous timbral/tonal features and needs the locked analysis environment plus a BPM seed or same-source `analysis.json` tempo; requesting it does not install dependencies. Select the analysis interpreter explicitly when needed, following the tool contract. Recurrence scores are heuristic, not calibrated probabilities.

## Guitar-specific interpretation

Deathcore repetitions, tempo changes, meter shifts and long sweeps complicate boundaries. Similar envelopes or MFCC/chroma features need not imply identical notes. The optional backend uses 4/8/16-pulse recurrence proposals and a four-pulse bar proxy; this does not confirm a time signature. Breakdown/low-register-riff or brightening-texture labels are hypotheses; picking technique needs listening evidence. The operator confirmed “phase mistakes” means musical phrase mistakes. Signal-phase troubleshooting is outside this workflow.

Consume denoising and candidate/confirmed click-BPM evidence first, then nullable pitch/tonal context, repeated-pattern proposals and recurrence comparisons. Do not let unknown tonic/mode or absent intended phrases block segmentation. Compare recurring regions for duration and onset-motif differences, and surface possible incomplete phrases, loop start/end differences, skips, rushes or unclear spans as timestamped hypotheses with comparative evidence. A repeated region provides a self-consistency baseline, not proof that its first rendition was correct.

Use the pipeline skill to collect automatic candidates and compare an approved reference when one exists, then the marker skill for generic source-time CSV/JSON export. Definite mistake or missed/extra-note grading requires expected intent plus listening/calibration evidence. Semantic phrase correctness, learned tonic/mode and native editor imports remain beyond the pilot.

**Review scenario:** With only a take and confirmed tempo, discover repeating chug groups and possible breakdown transitions. Flag a shorter recurrence or changed onset motif for review without demanding a score or declaring it wrong; preserve possible intentional variation.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
