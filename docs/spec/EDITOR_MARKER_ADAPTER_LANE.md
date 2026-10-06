# Source-time editor marker adapter lane

Recorded October 5, 2026. Owner: `resolve_marker_sources`; integration: root.
Authority: operator-authorized parallel week feature design;
R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13. This is a dry-run design and bounded
local inventory, not an implemented native adapter or editor import.

## Deliverable and current evidence

Implement a future local coordinate planner and native-format previews using the
[existing compatibility specification](EDITOR_MARKER_SPIKE.md) and
[primary-source research](../research/EDITOR_MARKERS.md). Keep generic markers as
canonical input; generated native coordinates never replace source seconds.
No editor process, project connection, app installation, metadata registration,
import, marker write, or host configuration change belongs to this lane.

The read-only inventory found no Final Cut Pro or Resolve in the inspected
standard system/user app directories, Home Manager app links, or scoped
Spotlight bundle-ID results. Conventional Resolve SDK directories were absent.
Application version/build/edition and current Resolve marker API contract are
therefore unknown; this is not an exhaustive disk search. The
[dated inventory receipt](../agent-notes/2026-10-05-editor-marker-adapter-inventory.md)
records paths and limitations.

Current run `20261005T232741Z-2b5dc43fd009` contains **180 generic markers** and a
hash-bound **24-marker** review selection, with 156 exclusions and 25 composed
video callouts. Six selected observations were entirely suppressed by the video
overlap priority. Native planning must retain all 24 selected observations,
including suppressed ones, and report every exclusion; a video compositor's
visibility is not marker eligibility. Exact source intervals come from generic
markers and selection evidence, never the preview's centisecond subtitle/dwell
times. The actual preview receipt proves preserved 3,621 decoded VFR timestamps
from 0 through video extent 150.885 s and preserved delivery audio; it does not
prove editor conforming or performance correctness.

## Future interfaces and deterministic behavior

Proposed operator entrypoints, to be implemented and routed through `just`:

```text
just editor-marker-plan <run-dir> <selection-json> <editor-profile-json>
just editor-marker-preview <plan-json> <output-dir>
```

The first command verifies inputs and produces an immutable local
`editor-marker-plan.json` plus an exact-coordinate sidecar. The second serializes
fixture FCPXML or a Resolve operation preview only from a valid matching plan;
it never connects to an editor. These names are design targets, not working
recipes. No `apply` command is included in this milestone.

- Inputs: existing source-bound marker JSON, run manifest, explicit selection
  containing marker IDs, decoded PTS table, and an explicit editor profile. Bind
  every input by SHA-256; reject stale, escaping or symlinked input paths using
  the existing marker export policy. Do not infer the newest run or silently
  select a subset. The current 24-item selection is the real-take fixture.
- Profile: application/version/build/edition, chosen schema/API document digest,
  source hash, target original-or-derivative hash, verified source-to-target map,
  source presentation origin, corresponding asset-local origin, clip in/out,
  exact host frame duration, frame-ID origin, timecode origin/display mode, and
  calibration evidence. Missing host fields stay null; never default them from
  `avg_frame_rate`, filename, or displayed timecode.
- Plan: schema/exporter versions, input/profile hashes, explicit selected and
  excluded IDs, exact source times, preview PTS indices, nullable host positions,
  quantization errors, conflicts, uncertainty text, and per-marker disposition.
  Plan states are `calibration_required`, `fixture_only`, or
  `calibrated_preview_ready`; none means imported or accepted.
- Bounds: at most 50,000 input flags and 1,000 resulting native markers, including
  FCP span endpoint expansion. Exceeding either produces an explicit
  `selection_required` result; no truncation. Output uses a fresh directory and
  leaves source, existing runs, editor libraries, and user markers unchanged.
- Without a verified host profile, emit source-coordinate plans and hypothetical
  grid calculations marked `fixture_only`; host frame IDs remain null and no
  execution-ready Resolve payload or real-take FCPXML is emitted. A synthetic
  explicit profile can exercise serialization, with fixture labeling throughout.

## Coordinates, native previews, and uncertainty

Preserve source decimal timestamps as exact decimal rationals; this does not
invent sample accuracy. If source samples are provided, use verified audio
origin `A + n/Fs` exactly once. For source origin `P0`, corresponding editor
asset origin `C0`, local clip in `I`, and parent placement `O`:

```text
asset_local(s) = C0 + (s - P0)
parent_time(s) = O + (asset_local(s) - I)
```

Source PTS indices identify preview frames, not host frame IDs. Require a
version-bound host conform map for VFR. Do not divide frame index by the take's
average rate `108930/4549`, reinterpret it as 23.976, or assume the nominal
`24/1` establishes uniform picture cadence. Unsupported retiming, reversal,
nesting, missing PTS coverage, and unverified derivative maps abstain.

For a verified uniform host grid with origin `G` and period `D`, points round
`(local-G)/D` to nearest integer, with half ties toward the later frame. Spans
use floor at start and ceiling at exclusive end, retaining the original
half-open interval and signed boundary errors. These are repository policies;
current Resolve argument acceptance and frame-origin semantics are unverified.
Reject quantized coordinates outside verified clip/media coverage instead of
clamping. A flag in the audio tail beyond measured video extent stays in the
sidecar as `outside_video_coverage`.

**FCPXML:** Use the published DTD 1.10 as a source fixture profile, reduced
rational seconds, and a source/browser `asset-clip`. Obtain a host-exported
minimal clip template in a future calibration session before real-take output.
Ordinary markers represent points with one clip-format video-frame duration;
phrase spans become paired START/END points sharing the original ID. Do not
invent visible range markers, ratings, completed to-dos, or chapter semantics.
An exclusive end exactly at clip out uses the documented sidecar boundary
representation from the existing spike, or abstains. Serialize escaped local
media URLs and XML text; do not copy/embed media or register metadata keys.

Apple documents rational seconds and possible import gaps when timing misses
the containing frame grid, one-frame FCPXML markers, and the distinction between
DTD validity and successful import. [Timing attributes](https://developer.apple.com/documentation/professional-video-applications/timing-attributes),
[annotation semantics](https://developer.apple.com/documentation/professional-video-applications/associating-ratings-keywords-markers-and-metadata-with-media),
[DTD 1.10](https://developer.apple.com/documentation/professional-video-applications/document-type-definition).

**Resolve:** Plan source annotations for an explicitly selected `MediaPoolItem`,
not `Timeline` or arbitrary timeline-item coordinates. Treat the proposed
`AddMarker(frameId,color,name,note,duration,customData)` call as an interface to
verify against the installed manufacturer's SDK, not a current confirmed
contract. Until its document, types, duration units, frame origin, colors,
custom-data behavior and readback are verified, operations remain descriptive
intent objects with `executable=false`. Generic CSV, ADR cue-list CSV, and
timeline marker EDL are distinct workflows. [Blackmagic staff SDK guidance](https://forum.blackmagicdesign.com/viewtopic.php?f=21&t=205175).

One host coordinate can collapse multiple distinct observations. Default to a
reported same-frame conflict; do not shift, combine, suppress or overwrite.
Exact duplicate source/evidence IDs deduplicate only when contents also agree.
A future read-only existing-marker snapshot must be hash-bound before writable
planning; preserve all user markers. Repeat of an identical owned marker is a
no-op, while changed owned content is a conflict. No current host snapshot is
available, so current plans explicitly mark existing-marker inspection pending.

Titles use `REVIEW · possible phrase · <id>` or
`COMPARE · recurrence differs · <id>`. Notes retain `needs_review`, original
times, confidence kind, alternative explanations, comparison partner, source
hash prefix, and quantization error. Keep detailed arrays in the sidecar. A
score/similarity is not a calibrated probability; a marker cannot turn distorted
harmonics, legato/tapping/sweeps, or recurrence variation into a confirmed missed
note, rushed beat, wrong note, meter or tonic.

## Acceptance and next-week allocation

Implement source-only planning/serialization within existing day-six annotation
and day-seven handoff work; no extra hours beyond the approved 35+35-hour plan.
Source checks cover:

- Nonzero/negative audio origin without double addition; source origin −0.5 s,
  event −0.2 s maps to local 0.3 s when `C0=0`.
- Local in 5 s, marker 8 s, parent placement 10 s maps to parent 13 s; one-hour
  displayed timeline timecode does not change source-clip coordinates.
- Explicit 24 versus `24000/1001` rational grids; 24-fps point tie at `1/48` s;
  narrow outward spans and endpoint errors; missing host origin stays null.
- VFR PTS `[0,25,49,75]/600`; the real take's last decoded extent 150.885 s;
  audio-only event at 150.90 s; absent or duplicated/nonmonotonic PTS rejects
  native mapping without silently padding, freezing or changing audio.
- All current 24 selections, including six hidden preview observations, remain
  accounted for; 156 exclusions and all original 180 IDs are traceable.
- Same-frame and preexisting-user conflicts, repeat plans, stale hashes,
  bounded counts, Unicode/XML special characters, safe URL serialization,
  sidecar round-trip, and exact selected-version DTD validation.

These tests are proposed, not run here. App validation remains a separate future
session with the exact host build/edition and a disposable selected review clip:
first/middle/last marker checks, nonzero/trimmed origins, VFR and tail checks,
Resolve readback or FCPXML re-export comparison, and unchanged source/user
markers. Source validity, import success, visible marker alignment, listening
acceptance, and musical correctness remain separate states. If host access is
unavailable, complete the planner and fixtures and report native calibration
pending; no purchase, installation or host repair is implied.

## CLI implementation checkpoint, October 6 UTC

Root subsequently authorized a source-only worker and new tests. The first
entrypoint is now implemented as a CLI, with **stdout JSON only**:

```text
python3 scripts/editor_marker_plan.py <run-dir> <selection-relative-json> <profile-relative-json>
```

There is no `just`/MCP routing or native-format serializer yet. The worker emits
neither XML/import files nor executable API calls. Even a fixture profile with
all coordinate fields yields `native_contract_unverified`, `executable=false`,
and null `host_frame_id`; proposed host-calibrated states remain future work.
Pure `make_plan` accepts verified documents; CLI `build` additionally revalidates
the generic export against current flags/DAG/context and checks explicit profile
input digests before and after preparation. Original media is not rehashed or
decoded by this worker; output distinguishes manifest/graph source binding.

The initial profile uses `target` (`final_cut_pro` or `davinci_resolve`),
`source_sha256`, optional matching `target_sha256`, `mapping_kind=unretimed`,
nullable rational `source_origin`, `asset_origin`, `clip_in`, `clip_out`,
`parent_offset`, and optional `pts_artifact`. `input_sha256` must bind
`markers.json`, `manifest.json`, the chosen selection and any PTS artifact.
An optional **hypothetical** `fixture_grid` explicitly supplies `frame_duration`,
`origin` and integer `frame_id_origin`; it never supplies a native host mapping.
Optional `existing_markers` carry `fixture_frame_id` only and are expressly an
unverified fixture snapshot, not evidence of an editor read.

A PTS artifact binds `source_sha256`, declares
`clock=original_source_stream_timestamps_seconds`, provides positive rational
`time_base`, and has at most 120,000 `frames` with integer
`best_effort_timestamp` and positive integer `duration`. Duplicate/nonmonotonic
starts or unknown duration reject. A newer presentation supersedes the preceding
frame when reported duration overlaps; coverage cannot use that old duration to
bridge a later gap. JSON inputs are bounded at 20 MB each and 64 MB aggregate
including graph context; duplicate keys, NaN/infinity, numeric overflow, escaped
paths, stale content and symbolic-link artifacts reject. The existing source
IDs match the marked-preview stable ID algorithm; repeated identical selections
deduplicate, distinct same-frame observations remain reported conflicts.

FCP range previews produce an atomic START/END pair with one-frame duration;
an unrepresentable exclusive end suppresses both proposed actions and records
the boundary result. Resolve previews distinguish point from range and leave
the marker API unverified. Action bounds return `selection_required` with no
partial list. Neither collision case shifts timestamps or edits user metadata.
Before any fixture action, inverse-map quantized asset coordinates back to the
source clock and verify the entire expanded extent against the PTS intervals,
including the FCP END marker's one-frame extent. Original-interval coverage alone
does not establish that a snapped point or expanded range stays in video coverage.
Failed quantized coverage retains original/fixture errors and emits no action.

**Validation:** 16 new meaningful tests passed, including exact JSON-decimal time
preservation beyond binary-float precision. A pure, graph-verified check of
the actual 180-marker run retained 24 selections and 156 exclusions, with all
native and preview frame indices null and zero actions because the complete PTS
array is unavailable. The ending recurrence keeps original source interval
`149.6629213483146` to `150.961125` seconds and is outside the explicit
`150.885`-second clip bound. The independently audited frame-clock digest cannot
reconstruct full PTS membership. See the
[implementation receipt](../agent-notes/2026-10-06-editor-marker-plan-implementation.md)
for hashes, test command and separate application acceptance. The
[independent timing audit](../agent-notes/2026-10-06-editor-marker-timing-audit.md)
accepted the final freeze: **21 combined tests pass**, including five independent
regressions for quantized tails, VFR gaps, inverse origins and atomic FCP pairs.
It independently reproduced the actual metadata-plan counts and retained all six
preview-hidden observations. App import/calibration remains pending.

### Tool 26 admission closure

Root subsequently authorized metadata-only hook admission. The hook owner
forwards the three required CLI arguments with fixed `--summary`; no caller
command, arbitrary flags or executable profile is accepted. Run directory text
is bounded to 1-4096 characters; selection/profile paths are run-relative `.json`
names of 1-1024 characters. Full-plan stdout remains available when `--summary`
is omitted. Summary follows complete graph/profile/context validation and is
bounded to 64 KiB; validation and parser stderr are bounded to 16 KiB. This
worker still creates no plan/import files and invokes no editor.

The current profile is closed to `schema_version`, `source_sha256`, `target`,
`mapping_kind`, `target_sha256`, `source_origin`, `asset_origin`, `clip_in`,
`clip_out`, `parent_offset`, `fixture_grid`, `existing_markers`, `pts_artifact`,
and `input_sha256`. Optional schema version is integer 1, never boolean.
`fixture_grid` requires exactly `frame_duration`, `origin`, and `frame_id_origin`.
Existing-marker fixtures allow integer `fixture_frame_id` and optional `name`
text up to 256 characters; they remain unverified data. Digest-map roles are
exactly markers, manifest, selection, and optional PTS. Future SDK/calibration
fields need a separately admitted schema; unknown current fields, including
commands or executable flags, reject.

Summary `format=editor_marker_dry_run_summary` retains source/target/status,
`native_contract_unverified`, `executable=false`, source-identity scope,
marker/selected/excluded/action counts, disposition/collision counts, at most five
primary input hashes, complete context-digest checksum/count, and profile/worker
hashes. It contains no marker/evidence/action arrays and does not infer musical
acceptance from counts. Final admission closure passes 26 combined tests
(21 owner plus five independent timing regressions), including full validation
before summary, output/stderr bounds, closed nested/profile fields, exact digest
roles, and joint hook path limits. Hook/skill registration is owned separately.
