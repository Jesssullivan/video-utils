# Next parallel checkpoint: unified evidence graph

Authority: operator ten-hour parallel goal; R-HOOK-CONVERGENCE-20261004,
R-N11/R-N12/R-N13. This continues the existing horizon ending October6 at
06:49:34UTC, and adds no new weekly budget. Baseline signed source is
6f7d1965b3c99a9b2ed261d58ea8949c0d6a1b26. Nineteen tools and their skills are
published; local219-test suite passed. Hosted CI and listening remain separate.

| Lane | Owner | Exclusive files | Acceptance and dependency |
| --- | --- | --- | --- |
| Feature graph integration | phrase_dag | scripts/dag.py, tests/test_dag.py, docs/spec/GRAPH_FEATURES.md | Explicit bounded artifact selection for click/pitch/meter/tonal/comparison, source/upstream/settings hashes, stale/symlink rejection, nulls and sparse coverage retained; publish selector contract to report/hook lanes before coding dependent changes |
| Report integration | plan_review | scripts/report.py, tests/test_report.py, docs/spec/REPORT_FEATURES.md | Consume graph-verified evidence only; display unknowns, sampling coverage and candidate flags; no new media processing; depends on graph selector contract |
| Hook/skill integration | tool_hooks | program/tools.json, scripts/tool_api.py, tests/test_tool_contracts.py, docs/spec/GRAPH_TOOL_CONTRACT.md, .agents/skills/guitar-pipeline/SKILL.md | Expose optional evidence selectors through existing DAG tool; nineteen tools remain; strict bounded schema and exact skill readback; depends on graph contract |
| Corpus annotation | repo_patterns | scripts/corpus.py, tests/test_corpus.py, docs/spec/CORPUS_LANE.md | Bounded local manifest for explicitly labelled source spans and reviewer provenance; no generated labels passed off as musician truth, no model/audio downloads; separate fixture-vs-real evidence |
| Marker-format research | clip_baseline | docs/research/EDITOR_MARKERS.md, docs/spec/EDITOR_MARKER_SPIKE.md | Current primary-source FCPXML and Resolve marker semantics, VFR/source-time offsets, sample/frame rounding; source-only design and bounded fixtures, no application compatibility claim |
| Native parameter state | au_architecture | native/au-spike/state/**, docs/spec/AU_STATE.md | Isolated bounded state serialization/validation and restore-before-render experiment; existing native/automation files frozen; no plugin registration, host configuration or device operation |

Root integrates, reruns meaningful checks and the actual calibrated demo, records
factual Linear receipts, and owns publication. Owners must record definitions of
done and receipts before handoff. Existing tools may abstain; absence of verified
meter, tonic, metronome identity or intended notes must remain visible. New corpus
and development checks are not audio processing tools until explicitly integrated
with an API and skill. No guessed errors or ground truth may enter the report.
