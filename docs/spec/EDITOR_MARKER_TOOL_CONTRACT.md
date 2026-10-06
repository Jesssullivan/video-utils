# Source-time editor marker planning hook

Root admitted `editor_marker_plan` as tool twenty-six on October 6, 2026 after
independent CLI/timing audit and the compact-summary qualification. Authority:
operator-authorized parallel work, repository `AGENTS.md`,
R-HOOK-CONVERGENCE-20261004 and R-N13. The planner lane owns worker/profile
validation; the hook lane owns registry/dispatcher, this contract and related
tests; root owns publication and actual-run evidence. The previous twenty-five
descriptors are unchanged, verified against committed `f180572`.

The definition of done was recorded before advertising the operation: fixed
`--summary` after complete provenance/coordinate validation, compact <=64 KiB
result, closed profile data schema, explicit bounded local inputs/deadline,
actual MCP success/stale/unsafe/unknown-data tests and exact matching prompt
readback. This source-only operation invokes no editor and produces no native
import file or executable native action.

## Fixed interface and bounds

The dispatcher runs only
`scripts/editor_marker_plan.py RUN SELECTION PROFILE --summary`.
Fields are required `run_dir` (string 1–4096 characters), `selection` and `profile`
(strings 1–1024 each), plus optional integer `timeout_seconds` 1–120, default 120.
The run is an existing child of repository `artifacts/runs`; selection/profile
are explicit exact run-relative JSON paths. Absolute selectors, URLs, traversal,
symlink/staging components and duplicate input roles reject. No latest-run/subset
or profile discovery. The caller supplies no editor API, import/output filename,
executable map, argv, JSON profile object or schema definition.

The wrapper checks original run components before normalization, regular local
metadata paths and <=20 MB files. Worker inputs are <=20 MB each and <=64 MB
aggregate; generic/selected markers <=50,000, hypothetical actions <=1,000 and
PTS frames <=120,000. Every generic export is revalidated against current
flags/DAG/context and required primary profile digests before and after planning.
Summary projection follows full validation and is <=64 KiB; diagnostic stderr
is <=16 KiB including parser errors. The outer dispatcher owns the new bounded
process group under R-N11. Worker failure becomes a JSON MCP tool error; this
operation adds no capture-specific stdout-error parsing or previous-tool changes.

## Closed profile and clocks

Allowed profile fields are source_sha256, target, mapping_kind, target_sha256,
source_origin, asset_origin, clip_in, clip_out, parent_offset, fixture_grid,
existing_markers, pts_artifact, input_sha256 and optional schema_version (integer
1, never boolean). Target is final_cut_pro or davinci_resolve; only an unretimed
original-source map is supported. Unknown fields reject rather than becoming
editor/runtime configuration.

Fixture grid is exactly frame_duration/origin/frame_id_origin; positions are
hypothetical. Existing-marker entries contain fixture_frame_id plus optional
name (<=256 characters), with no executable operation keys. The digest map
contains exactly the three required primary roles—manifest, generic markers and
explicit selection—plus optional PTS, bound to current file bytes. A full PTS
artifact needs exact source hash, source-timestamp clock, positive rational
timebase and integer starts/positive durations. Nonmonotonic/duplicate frames,
gaps, missing origins, clip tails and expanded quantized coverage abstain.
A frame-clock digest or nominal/average rate cannot reconstruct full membership.

Original source decimal times remain exact rational values, not invented sample
or host accuracy. Source-to-asset and parent clocks remain distinct. Full source
observations—including preview-hidden selections—and every exclusion are
accounted for. Quantization/collisions do not shift, clamp or overwrite user
markers. Hypothetical FCP range endpoints are atomic; a rejected expanded
endpoint does not become a partial executable import.

## Result and evidence

Compact summary fields are schema_version, format
(editor_marker_dry_run_summary), scope, source_sha256, target, plan_status,
native_contract_status, executable, source_identity_verification, marker_count,
selected_count, excluded_count, action_count, disposition_counts,
collision_counts, input_sha256 (primary digests), input_artifact_count,
input_manifest_sha256 (complete context digest), profile_sha256 and worker_sha256.
It omits marker/action rows; the full validated plan remains available through
the direct CLI without `--summary`. No output files or source metadata change.

Native contract is always `native_contract_unverified`, `executable: false` and
native host frame IDs remain null. A nonzero fixture action count is descriptive,
not a runnable editor/API/import result. Original media is not rehashed or
decoded: identity is manifest/graph bound. Existing provenance bytes can be
hashed; no audio processing, network, editor connection or host repair occurs.
No confirmed notes/beats/phrases/mistakes, native import, listening or AU/Logic
acceptance follows from a successful metadata plan.

Final worker SHA-256 is
`0af933083cc5415eca6c2e3d367ec15ec68dfc7b7a511b4392725c120dff75be`.
Owner/timing qualification reports 26 combined tests. Six focused hook tests
passed in 5.105 seconds: actual initialized MCP metadata summaries, input
immutability, closed profile/fixture schemas, stale digests and non-finite data,
unsafe/missing/oversized paths, literal fixed argv and deadline, exact prompt,
and a 1,200-marker full plan larger than the dispatcher's 2 MiB pipe ceiling
successfully projected to a bounded summary after complete validation.
With PTS absent the fixture retained selected observations, zero actions and
unverified coverage. No FFmpeg/FFprobe was needed.

The combined local checkpoint passed **78/78 targeted tests**: 59 contracts
(81.218 seconds), 11 dispatcher tests (1.114 seconds) and 8 MCP tests (6.127
seconds), with no skips and explicit pinned media binaries for media checks.
The editor fixture was additionally extended to verify that a positive
hypothetical action count still returns native-unverified/executable-false;
the six editor tests passed again after that assertion.

A source-only copy, containing neither model weights nor isolated runtime and
using deliberately unavailable media binaries, passed twelve focused tests
with eleven passes and one explicitly labelled optional learned-inference skip.
That fixes an offline-checkout assumption exposed by hosted CI; no acquisition
occurs in tests. Missing-runtime rejection uses an explicitly mocked model
preflight rather than requiring real weights. Available-but-corrupt artifacts
are not skipped; actual inference must reject them. This source-only fixture
proof is distinct from root's hosted CI rerun or complete offline suite.

The skill lane independently passed all twenty-six bundled validators and
initialized stdio enumeration/exact readback of every prompt, with empty stderr.
Final editor skill SHA-256 is
`e4e47d5b21a54e9eeb94b3a1d2175711203968405c3cc85d8c627755ad3b3f03`.
The Basic Pitch skill's separately admitted prerequisite-only update was included
in the renewed twenty-six-prompt proof; it adds no model/interpreter arguments.

The separate historical actual-run proof retained 180 generic markers,
24 selected observations, 156 exclusions and zero actions/null frame indices
without a complete PTS table. It is not native host calibration. Root owns new
actual metadata proof, source publication and hosted CI receipts separately.
