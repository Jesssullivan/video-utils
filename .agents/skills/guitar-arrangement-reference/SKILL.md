---
name: guitar-arrangement-reference
description: Compare a source-bound supplied guitar arrangement with cached phrase boundaries, retaining approximate tempo, missing coverage and ambiguous alignment as review candidates without detecting clicks or grading performance.
---

# Compare an expected arrangement with cached evidence

**Hook:** MCP tool `arrangement_reference`, prompt `guitar-arrangement-reference`. The experimental typed route is available locally. Inspect `tools/list` for current schema and [the hook contract](../../../docs/spec/ARRANGEMENT_REFERENCE_TOOL_CONTRACT.md) for qualification. Local source/MCP evidence is separate from publication or musical acceptance; [the skill lane](../../../docs/spec/ARRANGEMENT_REFERENCE_SKILL_LANE.md) records checkpoints.

## Use and bounded inputs

Use this tool when the operator supplies expected section order, phrase counts and clicks per phrase for a particular source. Automatic phrase discovery remains available without an expected arrangement; do not turn a reference into fabricated observations or a prerequisite to segmentation.

The closed typed contract has required `run_dir` and `output`, strings 1–4,096 characters. Run is beneath repository `artifacts/runs`; output must be a fresh child directory of that exact selected run. Optional `reference`, string 1–4,096, defaults to `program/demo-arrangement.json`; it is an existing bounded local JSON file. Use the demo default only when its source identity and supplied intent match this run. `timeout_seconds` is integer 1–120/default 120. Reject traversal/symlink components and output reuse; no latest-run selection is implied. The selected-run output restriction is narrower than the standalone CLI's fresh local directory route.

Direct worker uses `python3 scripts/arrangement_reference.py REFERENCE --run-dir RUN --output NEW_DIR`. The direct fixture alternative `--observations JSON` is not a typed-hook field. No alignment-cost, tempo, threshold, model/runtime, filter or audio-processing override is exposed. Settings are fixed; refine legitimate reference inputs or recompute upstream evidence through their supported tools, then evaluate a fresh output.

## Keep intent and observations separate

Inspect the closed reference's source SHA, supplied provenance/authority reference, visible assumptions, approximate tempo, first-phrase anchor interval, click-start context and ordered phrase/breakdown/rest sections. Section counts and clicks per unit are expected intent, not extracted counts. A declared click tempo and half/double-time pulse candidate remain separate. Click units do not establish meter, musical bars, downbeats or note count.

Require coherent manifest/analysis/phrase hashes, canonical analyzed PCM identity, native timing/lineage and covered source extent. The run adapter hashes the current canonical PCM bytes and cached metadata; it does not rehash original encoded media or decode/extract new boundaries. Preserve that identity scope. Near-32 Hz nine-string distortion, rests, palm mutes, sweeps and legato can obscure novelty and attacks; absent boundaries cannot establish missed phrases or notes.

Monotonic partial matching retains near-optimal alternatives, unmatched possibilities, ambiguous observations and censored coverage. Read actual `observed` and uncertainty fields, not the reference's expected timestamps as detections. An intended-boundary marker can exist with null observed support. Unknown boundary latency/coverage prevents precise timing grades.

`reference_equivalent_clicks` means observed boundary duration divided by the supplied approximate period. It is not an event count; `observed_click_count` remains null. Preserve duration/offset ranges and null boundary-pair durations. Neither a matching quotient nor a count discrepancy proves a correct performance, rushed beat or skipped phrase.

## Interpret, research and iterate

Status `reference_conditioned_review_candidates` writes fresh `assessment.json`, `review-candidates.json` and `receipt.json` with input/output/settings/producer hashes. Flags remain `needs_review`, `performance_issue_confirmed:false`; meter is null. No DSP, learned model, new audio extraction, master adoption, listening acceptance or native-editor import is performed. Existing masters and upstream evidence remain intact.

Inspect candidate timestamps, expected-versus-observed basis, coverage and alignment alternatives before listening or asking a performance question. Research upstream phrase/tempo methods using repo primary-source notes. Recompute stale phrase evidence through its actual tool, or update a reference using newly supplied intent; retain previous source/reference/settings hashes and use fresh output. Do not move anchors/counts solely to improve agreement or describe supplied assumptions as discoveries. Confirm musical mistakes only with sufficient intended reference, calibrated evidence and actual listening.

Bounds: reference64KiB, manifest1MiB, analysis16MiB, phrases4MiB, canonical PCM1GiB; expected units <=128, observed boundaries <=2048. Assessment/review artifacts <=2MiB each, receipt64KiB; fixed alignment stage <=30 seconds inside the wrapper deadline. Compact stdout points to full artifacts. Deterministic randomized properties qualify metadata alignment/marker invariants, not end-to-end audio extraction or real musical accuracy. Keep source checks, cached assessment, marker review, actual listening and accepted master separate.
