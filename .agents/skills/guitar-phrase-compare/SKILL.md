---
name: guitar-phrase-compare
description: Compare discovered guitar recurrence windows with bounded feature alignment and relative timing diagnostics, preserving attack-edit uncertainty without requiring an intended score.
---

# Compare recurring guitar regions

**Hook:** MCP tool `phrase_compare` and MCP prompt `guitar-phrase-compare`; inspect `tools/list` for publication status and supported arguments. The bounded standard-library comparison worker is implemented.

## Use and controls

Use `phrase_compare` with `run_dir`. Controls: `max_pairs` 1–60 (default 30), `band_fraction` greater than 0 and at most 0.5 (default 0.20), `min_rate` 0.25–1 (default 0.5), `max_rate` 1–4 (default 2), and the bounded tool timeout. Recipe fallback after registry publication: `just tool-run phrase_compare '{"run_dir":"<run-dir>"}'`. Direct worker: `python3 scripts/phrase_compare.py "<run-dir>" [--max-pairs 30] [--band-fraction 0.20] [--min-rate 0.5] [--max-rate 2.0]`.

Read [the comparison contract and primary research](../../../docs/spec/PHRASE_COMPARE_LANE.md). Inputs are hash-consistent `manifest.json`, `analysis.librosa.features` and `phrases.recurrence_candidates`. If feature data or discovered recurrences are absent, obtain those upstream artifacts with supported workers; do not invent features or intended phrases. No score, tonic/mode or intended-rhythm reference is required for comparison.

The worker writes `phrase-comparisons.json` atomically and leaves media, DAG and marker files untouched. Inspect source/analysis/artifact/settings hashes and raw-versus-restored lineage. Work is capped at 384 frames per window, 100,000 band cells per pair and 2,000,000 cells per run.

## Alignment interpretation and iteration

Rate means elapsed second-phrase time per elapsed first-phrase time. Supported local steps are `(1,1)`, `(2,1)` and `(1,2)`; tighter rate constraints can remove off-diagonal steps and yield no path. Wider limits do not invent new steps. Treat no-path, uniform texture and weak mismatch evidence as abstention; never silently switch to an unconstrained alignment.

Inspect duration/rate changes, feature mismatch and sampled relative offsets before interpreting onset motifs. Feature alignment can skip frames without proving a deleted note. Detector/boundary confidence and legato context control attack-edit hypotheses: unknown/weak evidence must preserve diagnostics while abstaining from missed/extra-attack implications. Relative comparison is possible with unknown constant capture latency; detector and boundary bias remain.

Distorted nine-string harmonics, near-32 Hz fundamentals, palm mutes, triplets, tapping, legato and sweeps make chroma/MFCC similarity incomplete evidence. A repeated region may differ intentionally or contain an error in either rendition. All review flags remain `needs_review`; performance grading is absent. Neither a close path nor a hypothesis establishes identical notes or a musician mistake.

**Review scenario:** A compressed recurrence can show a relative duration change without an intended score. When its detector confidence is unknown, retain geometric timing evidence while abstaining from attack-edit labels; deliberate triplets/legato remain plausible.

## Agent iteration

Inspect recurrence boundaries and upstream detector evidence, propose one bounded control change, compare paths/abstentions against original playback, and retain settings plus hashes and limitations. Use primary sources linked from the comparison contract for uncertain DTW behavior. Follow [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for receipts, discovery and source-time evidence; never imply automatic rerendering, model installation or native editor import.
