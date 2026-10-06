# Editor marker export: worker and tool contract

Owner: S2 lane `editor_export` (sprint `20261006-s2`, Linear TIN-5606). The frozen
lane contract is [`sprints/EDITOR_EXPORT_S2.md`](sprints/EDITOR_EXPORT_S2.md), commit
`2579462`. Authority comes from the operator S2 resume prompt, repository `AGENTS.md`
and R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13. This document describes the
implemented worker (`scripts/editor_marker_export.py`), the timecode module
(`scripts/timecode.py`) and the proposed MCP hook `editor_marker_export`. Root
admits the hook from the lane's `root_owned_changes_requested`; until then the
hook is a draft
([descriptor draft](../agent-notes/sprints/20261006-s2/editor_export-tool-descriptor.json),
[skill draft](../../.agents/skills/editor-marker-export/SKILL.md)).

Nothing in this contract launches, connects to, writes to or imports into
Final Cut Pro or DaVinci Resolve. A written file is a **local review payload
whose host interpretation is unverified**.

## `scripts/timecode.py`

This module is pure standard-library integer and `Fraction` arithmetic. It does
no I/O and never converts through float.

| API | Behaviour |
| --- | --- |
| `parse_rate(value)` | Accepts an `int`, a `Fraction` or an `"N"`/`"N/D"` string. Allowed rates are `N/1` with 1 ≤ N ≤ 1000, or exactly `k·1000/1001` with 1 ≤ k ≤ 1000. A bool, float, non-numeric value, zero or negative raises `rate_invalid`. Any other positive rational (`108930/4549`, `24/1001`, `2997/100`, `1001/1`) raises `rate_unsupported`. |
| `Clock(rate, drop_frame)` | Holds the validated constants `nominal`, `drop` (= nominal/15 for DF: 2, 4 or 8), `per_minute`, `per_ten_minutes`, `per_day` and the `FF` width `digits = max(2, len(str(nominal−1)))`. DF is allowed only for `30000/1001`, `60000/1001` and `120000/1001`; any other DF request raises `drop_frame_rate_unsupported`. |
| `frame_to_timecode`, `timecode_to_frame`, `frame_to_fields` | These use closed-form TN2310 counting. The label grammar is `HH:MM:SS:FF` for NDF and `HH:MM:SS;FF` for DF, with ASCII digits only. Valid frames are `0 ≤ frame < per_day`, with no 24 h wrap. |
| `nominal_fps`, `drop_frame_allowed`, `dropped_per_minute`, `frames_per_day`, `frame_digits` | These derive their values from `Clock`. |

`TimecodeError(ValueError).reason` takes one value from a closed set:
`rate_invalid`, `rate_unsupported`, `drop_frame_rate_unsupported`,
`frame_out_of_range`, `label_malformed`, `label_field_out_of_range`,
`label_dropped_in_drop_frame` or `separator_mode_mismatch`. Labels are display
identifiers only. They never change media time, sample position or the rational
frame period: `24/1` and `24000/1001` share labels but keep distinct periods.

## `scripts/editor_marker_export.py`

```
python3 scripts/editor_marker_export.py RUN_DIR SELECTION EXPORT_PROFILE \
  --format {fcpxml,resolve_ops} --output-dir DIR [--dtd PATH] [--summary]
```

The exit status is `0` for a written export **and** for an abstention, which is
a valid result. Malformed, stale or unsafe input gives `1`, with stderr bounded
to 16 KiB. Parser errors give `2`.

### Inputs

`SELECTION` and `EXPORT_PROFILE` are exact run-relative JSON paths under the
planner's path policy. The export profile has a closed schema, and unknown keys
reject:

```json
{"schema_version": 1, "format": "editor_marker_export_profile",
 "plan_profile": "editor-profile.json", "plan_profile_sha256": "<64 hex>",
 "timecode": {"drop_frame": false, "origin_label": "00:00:00:00"},
 "fcpxml": {"event_name": "video-utils review", "asset_name": "take",
            "media_src_url": "file:///…%20…%E2%80%AF….mov", "width": null, "height": null}}
```

- `schema_version` must be the integer 1, never a bool.
- `plan_profile` must be digest-bound. A stale digest gives exit 1.
- `fcpxml` is required for `--format fcpxml` and refused for `resolve_ops`.
- `event_name` and `asset_name` are 1–256 XML-representable characters.
- `media_src_url` is null or an already percent-encoded absolute `file:///`
  URL of at most 4096 characters, with no raw spaces, U+202F, query or fragment.
  It is never derived from manifests. `file_url_from_path()` is a helper, and
  media is never copied.
- `width` and `height` are null or integers from 1 to 32768.

The planner profile target must match the format: `final_cut_pro` ↔ `fcpxml` and
`davinci_resolve` ↔ `resolve_ops`.

The worker calls `editor_marker_plan.build` unchanged, which verifies the
markers, manifest, flags, DAG, selection and PTS digests. It then re-reads
`markers.json`, so it can keep the original decimal lexemes, and the PTS artifact,
and requires both digests to equal the planner's.

### Uniform-grid gate

The `reasons[]` list uses a closed vocabulary in a fixed order. Each check below
either passes or adds its reason.

| Check | Reason on failure |
| --- | --- |
| Planner `plan_status` is `fixture_only` (over 1,000 actions → `selection_required`; no grid → `calibration_required`) | `plan_selection_required`, `plan_calibration_required` |
| The planner profile binds a complete PTS artifact | `cadence_unknown_no_pts` (`cadence: unknown`) |
| All frame durations are equal, and every successive start step equals that duration | `cadence_variable` (`cadence: variable`) |
| PTS period == grid `frame_duration` as exact rationals | `grid_pts_period_mismatch` |
| Every asset-local PTS start is an integer number of periods from the grid origin | `grid_origin_misaligned` |
| Source/asset origins and clip in/out are all present *(additive)* | `asset_mapping_unknown` |
| FCPXML: clip in/out lie on the grid *(additive)* | `clip_bounds_off_grid` |
| FCPXML: `asset_start ≤ clip_in < clip_out ≤ asset_end` (measured PTS coverage) *(additive)* | `clip_outside_asset_extent` |
| `1/frame_duration` passes `parse_rate` | `rate_unsupported_for_timecode` |
| DF requested only at a DF rate | `drop_frame_rate_unsupported` |
| FCPXML: `media_src_url` is present | `media_reference_missing` |
| No negative native time (FCPXML asset start, clip in, offset, marker starts; Resolve `frameId`, *additive*) | `negative_native_time_unverified` |

The checks that depend on a grid run only once cadence is measured uniform. A
VFR take therefore reports `cadence_variable` alone, and does not list derived
grid failures. The three *additive* checks are conservative abstentions beyond
the frozen contract. FCPXML timing that lies off the format grid, or outside the
asset, is known to provoke host gap or warning behaviour. The measured step and
duration histograms appear in `cadence_evidence` (class
`measured_source_pts_table`). Average or nominal metadata appears only as
`metadata_cadence_hint` (class `metadata_inference`, `used_for_decisions: false`).

`native_export_status` is decided in this order:

1. `selection_required` if the planner returned it.
2. Otherwise `calibration_required` if any reason was recorded.
3. Otherwise `nothing_exportable` if every action was excluded by a collision.
4. Otherwise `written_unverified`.

Only `written_unverified` creates anything. Every other status creates **no file
and no directory**.

### Collisions

Any planner action with `collision` of `preserve_existing_marker` or
`planned_same_frame_conflict` excludes **every** action of that `marker_id`. A
colliding START also removes its END. Excluded markers stay in the sidecar with
`exported: false` and an `exclusion_reason`. Nothing is shifted, merged or
overwritten.

### Written files

The worker computes the payload in memory. It then writes the payload into a
sibling `.<name>.staging-*` directory, runs the optional DTD validation, writes
the sidecar, re-hashes every input, and finally calls `os.rename` to move the
staging directory onto the absent `--output-dir`. An existing path is refused
before and again after staging. A residual race remains: POSIX `rename` can
replace an *empty* directory created in the instant between the last check and
the rename. On any failure the staging directory is removed. Output is
deterministic: it contains no wall-clock time and no output path, and stdout
reports the SHA-256 and byte count of every file.

- **`review.fcpxmld/Info.fcpxml`** (≤ 4 MiB) begins with the XML declaration and
  `<!DOCTYPE fcpxml>`, followed by `<fcpxml version="1.10">`. The structure is:
  - `resources/format id="r1"` with `frameDuration=D` and optional width/height.
  - `resources/asset id="r2"` with `start` = asset-local first PTS,
    `duration` = PTS coverage extent, `hasVideo="1"`, `format="r1"`, and a
    `media-rep kind="original-media" src=…` child.
  - `library/event name=…`, containing an `asset-clip ref="r2"` with
    `offset` = parent offset (or `0s`), `start` = clip_in,
    `duration` = clip_out − clip_in, `format="r1"` and `tcFormat` `NDF`/`DF`.

  Each exported planner action becomes `<marker start=… duration=D value=title
  note=…/>`, with notes ending `marker_id=…; role=…; fixture_frame_id=…
  (hypothetical, not a host frame)`. A span is the planner's START/END pair. No
  `completed` attribute, rating or chapter marker is written. Times are reduced
  rationals written as `Ns` or `n/ds`. Attribute escaping covers `& < > "` and
  encodes tab, LF and CR as character references, so text round-trips unchanged.
  XML-unrepresentable control characters give exit 1.
- **`resolve-operations.json`** has `format: resolve_marker_operations_preview`,
  `executable: false`, `api_contract: unverified`, `application_import:
  not_performed`, `resolve_version: null`, `receiver:
  explicit_original_MediaPoolItem` and `frame_id_basis:
  fixture_grid_frame_id_origin_unverified_against_host`. Each entry in
  `operations[]` has `frameId` (int), `duration_frames` (int ≥ 1), `name`,
  `note`, `custom_data = marker_id`, `color: null`, `executable: false`,
  `api_contract: unverified` and `host_frame_id: null`.
- **`editor-marker-export.sidecar.json`** (≤ 16 MiB) holds the result fields
  without `output_dir`, plus `payload_sha256`. It has one row for every selected
  marker. Each row has `marker_id`, `marker_index`, `kind`,
  `original_start_decimal`/`original_end_decimal` (the exact JSON lexemes),
  `source_*`, `asset_local_*`, `parent_time`, `preview_frame_index`,
  `fixture_start_frame`/`fixture_end_frame`, and
  `start_`/`end_quantization_error_seconds` as `{exact_seconds, display_ms}`
  (identical to the planner's signed errors). It also has
  `display_timecode_start`/`_end` with `display_timecode_status`, `collisions[]`,
  `disposition`, `exported`, `exclusion_reason`, `native_roles`,
  `host_frame_id: null`, `status: needs_review`, `confidence`, `title` and
  `notes`.

The display timecode frame is `(snapped_asset_local − asset_start)/D +
origin_frame`, where `origin_frame` is parsed from `timecode.origin_label` in the
selected DF/NDF mode. The basis is
`asset_local_from_asset_start_plus_profile_origin_unverified_against_host`. A
frame that is off the grid or outside 24 h is recorded as a null label with a
status, never wrapped.

### DTD validation

DTD validation runs only with `--dtd PATH`. The path must be a regular,
non-symlink local file of at most 1 MiB. Validation runs
`/usr/bin/xmllint --noout --nonet --dtdvalid PATH review.fcpxmld/Info.fcpxml` in
the staging directory, under a 30 s timeout. The result records the validator
path and version line, the DTD path and SHA-256, the return code and a 2,000-byte
diagnostics tail. The status is `passed`, `failed` (the bundle is still written,
and the failure is recorded) or `unavailable` (validator missing, timed out or
failed to start). Without `--dtd`, `dtd_validation` is `not_performed`. The MCP
hook exposes no DTD input. The lane never fetches Apple's DTD, and a synthetic
DTD does not establish FCPXML 1.10 conformance.

### Fixed status and unknown fields (result and sidecar)

These fields always carry the values shown: `application_import: not_performed`,
`native_contract_status: native_contract_unverified`, `executable: false`,
`api_contract: unverified`, `final_cut_version: null`, `resolve_version: null`,
`host_frame_id: null`, `display_timecode_basis` (as above), `listening_acceptance:
not_established` and `musical_verdict: not_established`. Markers inherit
`status: needs_review`. The worker never emits note-correctness, missed/extra-note
or mistake labels.

### Bounds

The exporter inherits the planner bounds: JSON inputs ≤ 20 MB each and ≤ 64 MB
in aggregate, ≤ 50,000 markers, ≤ 120,000 PTS frames and ≤ 1,000 actions with
no truncation. Its own bounds are Info.fcpxml ≤ 4 MiB, resolve-operations.json
and the sidecar ≤ 16 MiB each, `--summary` stdout ≤ 64 KiB (the summary omits
the per-marker rows and limitations) and stderr ≤ 16 KiB. Step and duration
histograms list at most 256 distinct values and flag any truncation. The DTD
check is the only subprocess, and it is bounded at 30 s.

## Proposed MCP hook `editor_marker_export` (root admission pending)

The inputs are `run_dir` (1–4096), `selection` and `profile` (1–1024 each),
`format` (`fcpxml` | `resolve_ops`) and `timeout_seconds` (integer 1–120,
default 120), with `additionalProperties: false`. There is no DTD, output path,
argv or inline-profile input. The dispatcher validates the paths the same way as
`editor_marker_plan`. It then runs the worker with `--summary` and an exclusive
output path `<run_dir>/editor-export-<format>-<sha256(export profile)[:12]>`,
which is a direct child of the run so that no parent directory has to be
created. An existing output rejects before the worker starts. The prompt
`editor-marker-export` is derived from the descriptor's `skill` path.

## Evidence classes

- **M** (measured): PTS cadence and histograms from a complete source table, and
  structural properties of the written files in fixtures.
- **I** (inference): metadata cadence hints.
- **U** (unverified): host import, native frame IDs, visible alignment, Resolve
  API behaviour and DTD conformance without a supplied DTD.
- **L** (listening): never claimed.

The real October 5, 2026 take is VFR. Its expected and recorded result is
`calibration_required` / `cadence: variable`. See
`docs/agent-notes/sprints/20261006-s2/editor_export-real-take-receipt.json`.
