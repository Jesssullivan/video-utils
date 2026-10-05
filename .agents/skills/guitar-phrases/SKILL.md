---
name: guitar-phrases
description: Suggest repeated regions and musical phrase boundaries in technical guitar; review incomplete phrases and loop alignment against a confirmed reference.
---

# Create reviewable phrase/repetition suggestions and reference-relative phrase markers.

**Hook:** MCP tool `phrases` and MCP prompt `guitar-phrases`. Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. Skill availability does not imply a server connection has been installed in this agent.

**Capability:** Experimental envelope/repetition suggestions and source-timestamped review spans. Same-source BPM/notes context is attached when available; musical form and intended phrases remain unconfirmed.

## Use and controls

Use MCP `phrases`; fallback: `just tool-run phrases '{"input":"<input>","run_dir":"<run-dir>"}'`. The direct worker is `python3 scripts/guitar_features.py phrases "<input>" --run-dir "<run-dir>"`. Listen around suggested boundaries, distinguish a mute/rest from a structural change, then annotate confirmed phrases.

The experimental worker accepts input/run directory only; it uses 0.5 s energy blocks for pause boundaries and 8 s envelope recurrence proposals. Window/repetition knobs are not yet exposed. Strength and recurrence are heuristics, not probabilities. Intended phrase starts/ends need reference annotations before calling a phrase mistake.

## Guitar-specific interpretation

Deathcore repetitions, tempo changes, meter shifts and long sweeps complicate boundaries. Similar envelopes need not imply identical notes. The operator confirmed “phase mistakes” means musical phrase mistakes. Signal-phase troubleshooting is outside this workflow.

For the week’s phrase workflow, consume denoising and candidate/confirmed click-BPM evidence first, then nullable tonic/mode/pitch evidence, repeated-pattern proposals and recurrence comparisons. Mark incomplete phrases, loop start/end mismatches, skips, rushes and unclear spans only when supported by explicit reference/context; include source timestamps and confidence. The current worker produces envelope suggestions and nullable review spans (`performance_issue` remains null), and reads same-source `analysis.json`/`notes.json` context. Use the pipeline skill for implemented experimental reference-relative attack/phrase comparisons, then the marker skill for generic source-time CSV/JSON export. Tonic/mode inference, semantic phrase grading, and native editor imports remain planned.

**Review scenario:** Repeated chugs with differing accent patterns may have similar envelopes; keep multiple plausible boundaries instead of declaring a compositional mistake.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
