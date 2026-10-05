---
name: guitar-phrase-evaluate
description: Evaluate hash-bound generated guitar phrase discovery and recurrence alignment with explicit boundary, coverage and warp metrics; keep synthetic agreement separate from real musical intent or performance acceptance.
---

# Evaluate generated phrase evidence

**Hook:** MCP tool `phrase_evaluate`, prompt `guitar-phrase-evaluate`. Inspect `tools/list` for the current locally available schema. The evaluator reads existing generated references and discovery artifacts; it does not run discovery, decode audio, train models or approve a real performance.

## Use and controls

Required `fixture_index`, `pilot_index` and `output` are paths of 1–4,096 characters. `timeout_seconds` is integer 1–900, default 120. Inputs must exist beneath the repository's `artifacts/benchmarks/`; output must be a new descendant directory. Reject unsafe paths rather than normalizing a rejected reference into a different file. There are no tolerance, score, backend, BPM or DTW controls on this evaluation hook.

Direct worker: `python3 scripts/phrase_evaluate.py --fixture-index "<bank-index>" --pilot-index "<phrase-pilot-index>" --output "<new-directory>" --summary`. Recipe: `just tool-run phrase_evaluate '{"fixture_index":"<bank-index>","pilot_index":"<phrase-pilot-index>","output":"<new-directory>"}'`. Read [the phrase calibration contract](../../../docs/spec/PHRASE_CALIBRATION_LANE.md).

## Inspect provenance before scores

Validate the schema-2 `technical-v2` bank, schema-1 pilot, current instrument registry, source/truth hashes and each analysis/phrase/comparison receipt. The pilot must account for each unique bank case. The bank is bounded to twelve cases and 120 generated seconds; JSON is bounded to 20 MB per file and 64 MB total. Matching has explicit item/edge limits and comparisons/path landmarks are bounded. Preserve structural rejection and changed-input findings.

Generated WAV bytes are read for hash/header and native sample extent checks; no waveform decoding or inference occurs. Native generator origin is explicit, not guessed from absent timestamps. Discovery and DTW must receive audio/settings only; attaching generator boundaries, score or warp landmarks before inference leaks the evaluation reference.

## Interpret measured agreement

Inspect compact stdout and the full `phrase-evaluation.json`, including `hard_gates_passed` and `unsupported_confirmed_claim_count`. Dispatch success or a low matched error cannot establish completion, good recall or musical acceptance.

Boundary windows are fixed at 20/50/100 ms with recording endpoints excluded. One-to-one matching maximizes count before minimizing displacement; duplicate estimates never earn repeated credit. Span/ordered recurrence IoU thresholds are 0.50/0.75. Retain raw counts, unmatched items, hierarchy levels, null semantic references and excluded fixture counts. Empty truth/estimates are not a perfect discovery score.

Compare phrase-relative rates, covered warp landmarks and both pre-warp differences and post-warp residuals. Producer median relative offset is not an affine shift intercept when rates differ. Unsupported landmarks remain uncovered; no extrapolation or fitted delay improves the result. A small DTW residual may show absorbed timing changes only where a changed landmark or both endpoints of a changed rate interval have path support. Changes outside that coverage remain unknown, not observed absorption or unchanged rhythm. Generated detectable attacks exclude omitted events and are distinct from legato/sweep pitch transitions.

Low recall, no path, unknown detector confidence and constrained alignment abstentions remain visible baselines. No generated reference agreement identifies musician intent, confirms a missed note, assigns meter or establishes listening acceptance in the phone take.

## Agent iteration

Inspect the task and fixed reference coverage, run the evaluator on frozen discovery receipts, then research matching/segmentation/DTW definitions through the contract's primary sources. To compare analysis knobs, run the owning discovery/comparison tool on fresh outputs with recorded settings and the same held-out truth; never change truth or tune on the real take's intended notes. Re-evaluate and retain hashes, denominators, exclusions and regressions. Follow [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for durable evidence and publication boundaries.
