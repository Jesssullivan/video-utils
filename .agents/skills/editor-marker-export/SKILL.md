---
name: editor-marker-export
description: Export source-timed guitar review markers as a local, non-executed FCPXML 1.10 bundle or DaVinci Resolve operations preview only when the editor grid is verified uniform against the complete source PTS table; abstain with calibration_required for VFR or unknown cadence.
---

# Export editor review markers

**Hook (admitted, experimental):** MCP tool `editor_marker_export`, prompt `editor-marker-export`. The worker is `scripts/editor_marker_export.py`. It runs the existing planner (`editor_marker_plan`) unchanged and then applies a uniform-grid gate. Only a fully verified plan becomes `review.fcpxmld/Info.fcpxml` or `resolve-operations.json`, written with `editor-marker-export.sidecar.json`. Nothing launches, connects to, writes to or imports into Final Cut Pro or DaVinci Resolve. `application_import` is always `not_performed`, `executable` is `false`, `api_contract` is `unverified`, `final_cut_version` and `resolve_version` are null, and `host_frame_id` is null on every row and operation.

## Inputs and controls

The required inputs are `run_dir` (1–4,096 characters, beneath `artifacts/runs/`), `selection` and `profile` (exact run-relative JSON, 1–1,024 characters each) and `format` (`fcpxml` or `resolve_ops`). The optional `timeout_seconds` is an integer from 1 to 120 and defaults to 120. The MCP hook passes no output path, DTD, argv or inline profile, so `dtd_validation` is always `not_performed` through MCP. The dispatcher validates `run_dir`, `selection` and `profile` exactly as `editor_marker_plan` does, then chooses a fresh `<run_dir>/editor-export-<format>-<export_profile_sha256[:12]>`, where the digest is the SHA-256 of the export profile file bytes. An existing path rejects before the worker starts. Operators can run `just editor-marker-export RUN SELECTION PROFILE FORMAT OUTPUT_DIR`.

The direct CLI is `python3 scripts/editor_marker_export.py RUN SELECTION EXPORT_PROFILE --format {fcpxml,resolve_ops} --output-dir DIR [--dtd PATH] [--summary]`.

`EXPORT_PROFILE` is a closed `editor_marker_export_profile` with these fields:
- `schema_version: 1`, an integer and never a bool.
- `plan_profile`, the run-relative planner profile, together with its exact `plan_profile_sha256`.
- `timecode {drop_frame, origin_label}`.
- For `fcpxml` only, `fcpxml {event_name, asset_name, media_src_url, width, height}`.

The `media_src_url` field is an explicit, already percent-encoded absolute `file:///` URL. It is never derived from manifests. Spaces and macOS U+202F become `%20` and `%E2%80%AF`. `file_url_from_path()` can produce it. Media is never copied or embedded. The `fcpxml` block is refused for `resolve_ops`, and unknown keys reject.

## Gate (all must hold or the result abstains with zero files)

1. Planner `plan_status` is `fixture_only`. The planner's `calibration_required` and `selection_required` statuses propagate (the latter means more than 1,000 actions, with no truncation).
2. The planner profile binds a complete PTS artifact. Without one the result is `cadence: unknown` with `cadence_unknown_no_pts`.
3. Every PTS frame has the same duration, and every successive step equals it. Otherwise the result is `cadence: variable` with `cadence_variable`. The measured step and duration histograms are recorded as evidence.
4. The PTS period equals the grid `frame_duration` exactly (otherwise `grid_pts_period_mismatch`). Every asset-local PTS start lies on the grid (otherwise `grid_origin_misaligned`).
5. `1/frame_duration` is an integer or `N*1000/1001` rate (otherwise `rate_unsupported_for_timecode`). DF is allowed only at 29.97, 59.94 and 119.88 (otherwise `drop_frame_rate_unsupported`).
6. FCPXML only: the media URL must be present (otherwise `media_reference_missing`), native times must not be negative (otherwise `negative_native_time_unverified`), and the clip in/out must lie on the grid inside the measured asset extent (otherwise `clip_bounds_off_grid` or `clip_outside_asset_extent`).
7. Missing source/asset origins or clip bounds give `asset_mapping_unknown`.

Average/nominal metadata (for example `108930/4549` versus `24/1`) appears only as `metadata_cadence_hint` with `used_for_decisions: false`. The October 5, 2026 take is VFR, with 24/25/26-tick steps at `1/600`, so it abstains. That abstention is the correct result, not a failure to work around.

## Outputs when written (`native_export_status: written_unverified`)

- FCPXML 1.10 has a `<!DOCTYPE fcpxml>` and reduced rational `Ns`/`n/ds` times. It contains one `format`, an `asset` with an `original-media` `media-rep`, and an event `asset-clip` with `tcFormat` DF/NDF. Each marker lasts one frame, and a span becomes a START/END pair whose notes share the `marker_id`. Only ordinary markers are written: no `completed` attribute, ratings or chapter markers.
- Resolve operations go to `explicit_original_MediaPoolItem`. Each operation has an int `frameId`, an int `duration_frames` of at least 1, `custom_data = marker_id` and `color: null`. The preview is not runnable.
- The sidecar has one row per selected marker, exported or not. Each row records the original JSON decimal lexeme, source and asset-local rationals, fixture frames, exact quantization errors with an ms display, display timecode labels, collisions, the disposition, `exported` and `exclusion_reason`. The `display_timecode_basis` is `asset_local_from_asset_start_plus_profile_origin_unverified_against_host`.

Collisions with existing or same-frame markers exclude every action of that `marker_id` atomically. Excluded markers stay in the sidecar and are never shifted, merged or overwritten. If no actions remain, the status is `nothing_exportable` and no files are written. Output is staged in a sibling directory and atomically renamed. It is byte-deterministic, with no timestamps, and output SHA-256 values appear in stdout. `--dtd PATH` (CLI only) validates with `/usr/bin/xmllint --nonet` against a supplied local DTD under a 30 s limit. A synthetic DTD does not establish FCPXML 1.10 conformance, and this tool never fetches Apple's DTD.

## Evidence discipline

Keep three claim classes separate: measured PTS cadence, structural checks of written files, and the unverified host interpretation. Valid XML is not an import. Markers stay `needs_review` hypotheses. Distorted near-32 Hz nine-string harmonics, palm mutes, rests, tuplets, tapping, sweeps and legato make attack and phrase boundaries ambiguous. Frame snapping must not hide the original source times, and no output establishes intended notes, missed or extra notes, mistakes, meter, tonic or listening acceptance (`listening_acceptance` and `musical_verdict` are `not_established`).

When iterating, change one explicit planner or export profile file at a time with updated digests. Compare reasons, cadence evidence and excluded rows, and keep abstentions in durable receipts. Host calibration (an exported template clip, the installed SDK version and readback) is separate future evidence. Read [the export contract](../../../docs/spec/EDITOR_MARKER_EXPORT.md), [the planner skill](../editor-marker-plan/SKILL.md) and [the primary-source research](../../../docs/research/EDITOR_MARKERS.md).
