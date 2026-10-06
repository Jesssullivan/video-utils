---
name: editor-marker-plan
description: Plan source-timed guitar review markers as bounded metadata for Final Cut Pro or DaVinci Resolve, keeping hypothetical coordinates separate from unverified native import and preserving VFR coverage uncertainty.
---

# Plan editor review markers

**Hook:** MCP tool `editor_marker_plan`, prompt `editor-marker-plan`. Launch `just mcp` and inspect `tools/list` for the current closed schema. This primitive validates existing metadata and returns a compact plan summary. Every target remains `native_contract_unverified` and `executable=false`; no editor connection, project inspection/write, import file, native action, media decode/render or audio acceptance is performed.

## Paths and supported controls

Required `run_dir` is 1–4,096 characters beneath repository `artifacts/runs/`. Required `selection` and `profile` are exact run-relative JSON artifact paths, 1–1,024 characters each. Reject traversal, symbolic links, URLs and staging artifacts. Explicitly select the run and files; never infer the latest run or choose a hidden subset. Optional `timeout_seconds` is integer 1–120/default 120. No target application, output file, executable, command, import or arbitrary mapping field is passed through MCP.

The fixed direct CLI is `python3 scripts/editor_marker_plan.py "<run-dir>" "<selection-relative.json>" "<profile-relative.json>" --summary`. It performs full metadata validation before summarizing. `just tool-run editor_marker_plan '<arguments-json>'` uses the typed hook. Read [the worker interface](../../../docs/spec/EDITOR_MARKER_ADAPTER_LANE.md) and [the hook contract](../../../docs/spec/EDITOR_MARKER_TOOL_CONTRACT.md) for the supported closed profile and summary.

Verify `markers.json` against current flags/graph, manifest and instrument context. The profile must bind marker, manifest, explicit selection and optional PTS artifact hashes. Source binding is manifest/graph evidence: original media is not freshly rehashed or decoded by this tool. Changed metadata, stale IDs/digests and malformed/nonfinite JSON reject; successful dispatch is not proof of source-media decoding or native import.

## Exact source coordinates and honest unknowns

Keep canonical original source intervals and selected/excluded IDs, including selected observations entirely hidden by preview composition. Do not substitute clipped subtitle spans, subtitle centiseconds or preview dwell times. Matching source/evidence duplicate selections deduplicate; distinct observations remain traceable.

The profile chooses `final_cut_pro` or `davinci_resolve` and an original-source, unretimed mapping. Derivative maps, retiming and nesting are unsupported. Explicit rational source/asset origins, clip in/out and parent offset may be nullable. Apply source-to-asset mapping once, then parent placement separately; preserve negative origins. Missing origins stay unknown. Average/nominal frame rate, displayed timecode and filenames never supply missing coordinates.

Only a complete, explicitly source-bound PTS artifact establishes preview frame containment: fixed original-source clock, positive rational time base, ordered unique integer starts and positive durations. A hash, sampled frames, header frame count or last extent cannot reconstruct that table. A newer frame supersedes an overlapping predecessor; its old duration cannot bridge a later gap. Preview indices are source containment evidence, not editor host frame IDs. `host_frame_id` remains null for all profiles, even complete fixture grids.

An explicit `fixture_grid` permits hypothetical uniform-grid calculations only. Point ties round toward the later frame; ranges round outward while retaining original half-open spans and signed errors. Before any descriptive action, inverse-map its entire quantized extent into source time and require continuous picture and clip coverage. Original-point coverage alone is insufficient. Do not clamp, pad picture tails, fabricate frames or hide a gap.

FCP range fixtures use an atomic START/END pair of one-frame points. An unrepresentable exclusive end or missing coverage through the END point suppresses both actions. Resolve fixtures remain descriptive point/range intents. Planned same-frame and supplied existing-marker collisions are reported; never shift, merge, suppress or overwrite observations to resolve them. An existing-marker fixture is not an actual editor snapshot.

## Results, bounds and iteration

Read the nested plan status and counts rather than equating tool completion with readiness. `calibration_required`, `fixture_only` and `selection_required` all retain unverified native contracts and nonexecutable actions. Missing PTS/clip mapping, outside coverage and boundary/collision dispositions are useful abstentions. Selection overflow emits no partial action list. Compact `editor_marker_dry_run_summary` follows full validation and contains source/profile/worker/input hashes, counts and disposition/collision totals, with no marker/action rows. It is not an import payload or a persisted full plan. Omit `--summary` only in the direct CLI when exact per-marker diagnostics are needed; that still returns stdout JSON and creates no plan/import file.

Bounds are 20 MB per JSON artifact, 64 MB aggregate metadata, 50,000 input markers, 120,000 PTS frames and 1,000 descriptive actions including FCP pair expansion. Summary output is at most 64 KiB; diagnostics are at most 16 KiB. Do not evade limits by silent truncation. Preserve input/profile/worker hashes and source intervals in a durable receipt; source, media, existing run artifacts, projects and user markers stay unchanged.

Inspect source-clock and selection evidence, research uncertain coordinate semantics in [primary-source editor research](../../../docs/research/EDITOR_MARKERS.md), then change one explicitly supported selection or fixture-profile setting in a separately named file with updated digests. Compare dispositions, errors and retained IDs; retain failures. Native SDK/version calibration, import/readback and visible alignment are separate future evidence, never promoted from a successful metadata plan.

Guitar markers remain `needs_review`: distorted near-32 Hz harmonics, rests, tuplets, tapping, sweeps and legato can make attack and phrase boundaries ambiguous. Quantization cannot establish intended notes, confirmed missed/rushed beats, meter, tonic or master/listening acceptance. Follow [the agent evidence contract](../../../docs/spec/AGENT_TOOLS.md) and abstain on unsupported native or musical claims.
