# S2 editor_export lane contract: FCPXML 1.10 and Resolve marker export

Status: **phase 1 contract freeze**. No code, numerics or media access ran in this phase.
Sprint `20261006-s2` (`program/sprints/20261006-s2.json`, lane `editor_export`,
workflow B wave 1); Linear TIN-5606 under parent TIN-5599, related TIN-5494/TIN-5492.
Authority: operator S2 resume prompt (`docs/agent-notes/2026-10-06-s2-resume.md`),
repository `AGENTS.md`, R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13.
Branch `sprint/20261006-s2/editor_export`, worktree
`.local/sprint2/editor_export`, baseline `4b87484`. Root signs merges, admits
tools/skills, writes Linear and publishes; this lane never pushes or merges.

## Scope

Turn a validated `editor_marker_plan` result whose editor grid is **verified
uniform** into local, non-executed native review payloads, and abstain for
everything else:

1. `scripts/timecode.py`: exact frame index ↔ display timecode for any integer
   rate or 1001-denominator rate. NDF everywhere; DF only for `30000/1001`,
   `60000/1001` and `120000/1001`. All other DF requests are refused with a typed reason.
2. `scripts/editor_marker_export.py`: calls the existing planner
   (`editor_marker_plan.build` / `make_plan`, unchanged) and then writes either
   `review.fcpxmld/Info.fcpxml` (FCPXML 1.10) or `resolve-operations.json`, plus
   a sidecar JSON. For the real VFR take it writes **no file** and returns
   `native_export_status: calibration_required`, `cadence: variable`.
3. A tool descriptor and skill draft in lane-owned paths. Root inserts the
   registry, dispatcher, prompt and recipe from `root_owned_changes_requested`.

Out of scope: editor installation, launch, connection, project write or import;
Resolve scripting execution; downloading Apple's DTD or the Resolve SDK; changes
to `scripts/editor_marker_plan.py`, `scripts/markers.py` or any root-owned file;
retiming/derivative/nested mappings; marker ratings, chapter markers or `completed`.
Application import stays `not_performed`.

## Owned files

| Path | Phase |
| --- | --- |
| `docs/spec/sprints/EDITOR_EXPORT_S2.md` (this file) | 1 |
| `scripts/timecode.py` | 2 |
| `scripts/editor_marker_export.py` | 2 |
| `tests/test_timecode.py` | 2 |
| `tests/test_editor_marker_export.py` | 2 |
| `docs/spec/EDITOR_MARKER_EXPORT.md` (worker/tool contract) | 2 |
| `.agents/skills/editor-marker-export/SKILL.md` (draft) | 2 |
| `docs/agent-notes/sprints/20261006-s2/editor_export-*.json` (descriptor draft, receipts) | 2–3 |

Ignored local outputs go only under `artifacts/s2/editor_export/` in this
worktree. Accepted `artifacts/runs/*` directories, the original take in
`~/Documents`, and Desktop exports are read-only.

## Reused interfaces (read-only)

- `editor_marker_plan.make_plan/build/rational/ratio/pts_table/covered/marker_id/read_json`.
  The planner's closed profile, `plan_status` (`fixture_only`, `calibration_required`,
  `selection_required`), `native_contract_status: native_contract_unverified`,
  `executable: false`, `host_frame_id: null`, actions, roles (`POINT`/`START`/`END`
  for FCP, `point`/`range` for Resolve) and collision labels are inherited, never
  redefined. `SourceDecimal` keeps the original JSON lexeme for the sidecar.
- Coordinate rules 1–6 in `docs/spec/EDITOR_MARKER_SPIKE.md`: source → asset-local
  mapping happens once, parent placement separately, point ties round later, spans
  round outward, and nothing is clamped or padded.
- `docs/research/EDITOR_MARKERS.md`: DTD 1.10 as the fixture profile, `.fcpxmld`
  bundle containing `Info.fcpxml`, START/END pair for spans, explicit original
  `MediaPoolItem` receiver for Resolve, TN2310 DF semantics.
- Measured PTS extraction pattern: `scripts/marked_video.py inspect_media`
  (`-show_frames -show_entries frame=best_effort_timestamp,duration`).

## Interfaces to implement (phase 2)

### `scripts/timecode.py` (pure, stdlib, no I/O)

- `TimecodeError(ValueError)` with `.reason` from the closed set:
  `rate_invalid`, `rate_unsupported`, `drop_frame_rate_unsupported`,
  `frame_out_of_range`, `label_malformed`, `label_field_out_of_range`,
  `label_dropped_in_drop_frame`, `separator_mode_mismatch`.
- `parse_rate(value) -> Fraction`: accepts int, `Fraction`, or `"N"`/`"N/D"`
  strings. Allowed values, after reduction, are `N/1` with `1 <= N <= 1000`, or
  `N/1001` with `N % 1000 == 0` and `1 <= N/1000 <= 1000`. Anything else, such as
  `108930/4549`, `24/1001` or `2997/100`, raises `rate_unsupported`.
  Bool, non-finite, zero and negative values raise `rate_invalid`.
- `nominal_fps(rate) -> int`: `N` for `N/1`, `N/1000` for `N/1001`.
- `drop_frame_allowed(rate) -> bool`: true only for the three DF rates.
- `dropped_per_minute(rate) -> int`: `nominal/15`, which gives 2, 4 and 8. DF only.
- `frames_per_day(rate, drop_frame) -> int`.
- `frame_to_timecode(frame, rate, drop_frame=False) -> str` and
  `timecode_to_frame(label, rate, drop_frame=False) -> int`. Closed-form
  arithmetic is used, and float conversions are never involved.
- Label grammar: `HH:MM:SS:FF` (NDF) or `HH:MM:SS;FF` (DF, `;` before frames only),
  `HH` 00–23. `FF` is zero-padded to `max(2, len(str(nominal-1)))` digits, which is
  three digits at 100–1000 fps. Valid frames are `0 <= frame < frames_per_day`.
  There is no 24 h wrap and negative frames are refused (`frame_out_of_range`).
  Parsing is strict. Dropped DF labels (`;00`..`;0k-1` at second 00 of minutes not
  divisible by 10) raise `label_dropped_in_drop_frame`. A wrong separator raises
  `separator_mode_mismatch`.
- Timecode labels are display identifiers only. They never change media time,
  sample position or the rational frame period.

### `scripts/editor_marker_export.py`

CLI: `python3 scripts/editor_marker_export.py RUN_DIR SELECTION PROFILE
--format {fcpxml,resolve_ops} --output-dir DIR [--dtd PATH] [--summary]`.
`SELECTION` and `PROFILE` are run-relative JSON paths, using the planner's
path policy.

**Export profile.** This is a closed schema and a separate file, so the planner
schema stays unchanged:

```json
{
  "schema_version": 1,
  "format": "editor_marker_export_profile",
  "plan_profile": "editor-profile.json",
  "plan_profile_sha256": "<64 hex>",
  "timecode": {"drop_frame": false, "origin_label": "00:00:00:00"},
  "fcpxml": {"event_name": "video-utils review", "asset_name": "take",
             "media_src_url": "file:///.../take.mov", "width": null, "height": null}
}
```

`plan_profile` is the existing closed planner profile, bound by digest.
`timecode.origin_label` uses the selected DF/NDF mode. `fcpxml` is required for
`--format fcpxml` and refused for `resolve_ops`. `media_src_url` must be an
explicit absolute `file://` URL with percent-encoding. It is never derived from
manifest paths, and no media is embedded or copied. Unknown keys, bool versions
and non-string or oversized text are rejected.

**Uniform-grid verification.** All of the following must hold, or the
export abstains:

1. Planner `plan_status == "fixture_only"`; `calibration_required` and
   `selection_required` propagate.
2. The planner profile names a complete hash-bound `pts_artifact`. With no
   artifact, the result is `cadence: unknown` and the reason `cadence_unknown_no_pts`.
3. Every PTS frame has the same positive duration `D_pts`, and every successive
   start step equals `D_pts` (no gaps or overlaps). Otherwise the result is
   `cadence: variable` and the reason `cadence_variable`. A step histogram is
   recorded as measurement evidence.
4. `D_pts == fixture_grid.frame_duration` exactly as a rational. Otherwise the
   reason is `grid_pts_period_mismatch`.
5. Each PTS start, mapped to asset-local time, lies on the grid
   (`(local − grid.origin)/D` is an integer). Otherwise the reason is
   `grid_origin_misaligned`.
6. `1/D` passes `parse_rate`. Otherwise the reason is `rate_unsupported_for_timecode`.
   DF requested at a non-DF rate gives `drop_frame_rate_unsupported`.
7. FCPXML only: `media_src_url` must be present, giving `media_reference_missing`
   otherwise, and every native time must be ≥ 0, giving
   `negative_native_time_unverified` otherwise.

Average/nominal rates, header frame counts and file names never satisfy
any check. The manifest's `avg_frame_rate != r_frame_rate` may be recorded as
`metadata_cadence_hint`, a metadata inference that is separate from measured cadence.

**Abstention.** If any check fails, the CLI creates **no file and no
directory**. Stdout JSON carries `native_export_status: calibration_required`,
`cadence`, the typed `reasons[]`, the planner summary counts and the input
hashes. Exit status is 0, because abstention is a valid result. Malformed or
stale input exits 1 with bounded stderr.

**Export.** When verification passes, the CLI stages files in a sibling temporary
directory and atomically renames it to `--output-dir`. That path must not exist;
an existing path is refused and never overwritten. It writes:

- `review.fcpxmld/Info.fcpxml`: `<?xml version="1.0" encoding="UTF-8"?>`,
  `<!DOCTYPE fcpxml>`, `<fcpxml version="1.10">`, then
  `resources/format` (`frameDuration=D`, optional width/height), then
  `resources/asset` (`start` = asset-local first PTS, `duration` = PTS coverage
  extent, `media-rep kind="original-media" src=…`), then
  `library/event/asset-clip` (`start=clip_in`, `duration=clip_out−clip_in`,
  `offset=parent_offset` or `0s`, `tcFormat` `NDF`/`DF`). Each planner FCP action
  becomes one `<marker start=… duration=D value=… note=…/>`. Every time is a
  reduced rational, written as `Ns` or `n/ds`. Markers last one frame, a span
  becomes its planner START/END pair, and **no `completed` attribute** is written.
  Ordinary markers only.
- `resolve-operations.json`: `format: resolve_marker_operations_preview`,
  `executable: false`, `api_contract: "unverified"`, `application_import:
  "not_performed"`, `resolve_version: null`, and `operations[]` with
  `receiver: explicit_original_MediaPoolItem`. Each entry has `frameId`
  (Python `int`, never bool or float), `duration_frames` (int ≥ 1), `name`,
  `note`, `custom_data` (= `marker_id`), `color: null`, `executable: false`,
  `api_contract: "unverified"` and `host_frame_id: null`.
- `editor-marker-export.sidecar.json`: one row for **every selected marker,
  exported or not**. Each row carries `marker_id`, `marker_index`,
  `original_start_decimal`/`original_end_decimal` (the exact JSON lexemes),
  `source_start`/`source_end` and `asset_local_start`/`asset_local_end`
  (rational strings), `fixture_start_frame`/`fixture_end_frame`,
  `start_quantization_error_seconds`/`end_quantization_error_seconds` (exact
  rationals plus a derived float-ms display), `display_timecode_start`/`_end`,
  `collisions[]`, `disposition`, `exported` (bool) and `exclusion_reason` (or
  null). It also records the top-level hashes listed under
  [Required unknown and status fields](#required-unknown-and-status-fields).

**Collisions.** `preserve_existing_marker` and `planned_same_frame_conflict`
actions are excluded from the native payload **atomically per `marker_id`**:
a colliding START also removes its END. They are kept in the sidecar with
`exported: false`. Actions are never shifted, merged or overwritten. If no
actions remain, the native status is `nothing_exportable` and no files
are written.

**Display timecode.** This is a sidecar label only. The display frame is
`(asset_local_position − asset_start)/D + origin_frames`, with basis
`asset_local_from_asset_start_plus_profile_origin_unverified_against_host`.

**DTD.** Validation runs only when `--dtd PATH` is supplied: a regular local file
≤ 1 MiB, non-symlink, checked with `/usr/bin/xmllint --noout --nonet --dtdvalid
PATH` under a 30 s timeout. The result records validator path, version, DTD
SHA-256 and status `passed`/`failed`/`unavailable`. Without `--dtd`, the status is
`dtd_validation: not_performed`. The MCP descriptor exposes no DTD input, so
MCP calls always record `not_performed`. The lane does not fetch Apple's DTD.

**Bounds.** These are inherited planner bounds plus Info.fcpxml ≤ 4 MiB, sidecar
≤ 16 MiB, `--summary` stdout ≤ 64 KiB and stderr ≤ 16 KiB. Output is
deterministic: identical inputs give byte-identical files, with no wall-clock
timestamps in payloads, and output SHA-256 values appear in stdout.

## Required unknown and status fields

The following fields must appear explicitly, with no omission and no default promotion:

| Field | Required value in this lane |
| --- | --- |
| `application_import` | `not_performed` (all formats, all outcomes) |
| `host_frame_id` | `null` on every sidecar row and Resolve operation |
| `native_contract_status` | `native_contract_unverified` |
| `executable` | `false` (top level and every operation) |
| `api_contract` (Resolve) | `unverified` |
| `resolve_version`, `final_cut_version` | `null` |
| `dtd_validation` | `not_performed` unless `--dtd`; then `passed`/`failed`/`unavailable` with validator identity |
| `native_export_status` | `written_unverified`, `calibration_required`, `nothing_exportable` or `selection_required` |
| `cadence` | `uniform`, `variable` or `unknown` (measured from the complete PTS table only) |
| `metadata_cadence_hint` | nullable inference from avg/nominal metadata, never used for decisions |
| `display_timecode_basis` | fixed unverified-basis string above |
| `listening_acceptance`, `musical_verdict` | `not_established` |
| Markers | inherit `status: needs_review`; no note-correctness, missed/extra-note or mistake labels |

## Real-take acceptance check (phase 2, predeclared)

Inputs are read-only. The take is `/Users/jess/Documents/Movie on 10-5-26 at 3.38 PM.mov`,
with source SHA-256 `a522115f…76c6`. Video `avg_frame_rate=108930/4549`,
`r_frame_rate=24/1`, time base `1/600`. Run `20261006T034521Z-a0def0c43eac`
has 171 generic markers and selection `reference-marked-preview-compact/selection.json`
with 71 selected markers. The accepted FULLER run `20261006T041633Z-990aa1bd6737` carries no
`markers.json`; it is cited for source identity only.

Procedure, with at most one heavy job at a time and explicit timeouts:

1. Run one bounded `$FFPROBE` decoded-frame scan (`best_effort_timestamp,duration`,
   timeout 300 s) and one streamed source SHA-256. Write
   `artifacts/s2/editor_export/real-take/pts.json` with the planner PTS schema
   (`clock: original_source_stream_timestamps_seconds`, `time_base: 1/600`).
2. Build a hash-verified metadata mirror under `artifacts/s2/editor_export/real-take/run/`.
   It holds byte-identical copies of `markers.json`, `manifest.json`, `flags.json`,
   `dag.json` and the DAG's hashed artifacts, plus the copied selection, a planner
   profile (`final_cut_pro`, source/asset origin 0, clip 0–150.954059, grid
   `1/24` nominal, `pts_artifact: pts.json`) and an export profile. If the mirror
   cannot pass `build`, fall back to pure `make_plan` on read-only loaded JSON and
   record `entrypoint: pure_make_plan`.
3. Run the exporter with `--format fcpxml` and with `--format resolve_ops`, plus a
   no-PTS arm.

Predeclared expected result: in all three arms the output directory does not
exist afterwards (zero files). The result reports `native_export_status:
calibration_required`, `cadence: variable` (`unknown` for the no-PTS arm) and
reason `cadence_variable` (`cadence_unknown_no_pts`), with
`application_import: not_performed` and `host_frame_id: null`. The previously
researched PTS histogram is 3,621 frames with steps of 24 ticks ×43, 25 ×3,528 and
26 ×49, and an extent of `90531/600` s. It is re-measured and compared, and any
difference is recorded rather than tuned around. Hashes of every read-only input
are identical before and after. The receipt goes in
`docs/agent-notes/sprints/20261006-s2/editor_export-real-take-receipt.json`.

## Test protocol

The commands run from the worktree root:
`PYTHONPATH=tests python3 -m unittest test_timecode -v` and
`PYTHONPATH=tests python3 -m unittest test_editor_marker_export -v`. Affected
regression: `PYTHONPATH=tests python3 -m unittest test_editor_marker_plan -v`.
Each command is wrapped in `timeout 600`. Fixtures are synthetic and in-memory
or in `tempfile` directories, and no test reads `~/Documents` or `artifacts/runs`.
Deterministic seed `20261006` applies wherever sampling is used.

### `tests/test_timecode.py` (≥ 10 tests)

1. **Exhaustive DF 24 h.** At `30000/1001`, `60000/1001` and `120000/1001`, every
   frame in `[0, frames_per_day)` (2,589,408 / 5,178,816 / 10,357,632) is checked
   against an independent odometer reference that increments labels and skips
   dropped labels. The checks are: closed-form label equals odometer label
   (correctness), `timecode_to_frame(label) == frame` (bijection), strictly
   increasing `(h,m,s,f)` tuples (monotonic), and unique labels.
2. **Skip property.** For each DF rate and all 1,440 minutes, labels `;00`…`;k−1`
   (k = 2/4/8) are absent at second 00 in the 1,296 minutes not divisible by 10,
   and present in the 144 that are. The labels per minute are `60·nominal − k` or
   `60·nominal`, respectively.
3. **TN2310 boundaries.** `00:00:59;29 → 00:01:00;02` (frames 1799→1800) and
   `00:09:59;29 → 00:10:00;00` (17981→17982) at 29.97. At 59.94, `00:00:59;59 →
   00:01:00;04`, and at 119.88, `00:00:59;119 → 00:01:00;008`.
4. **Exhaustive NDF 24 h.** At `24/1` (2,073,600 frames) and `30000/1001` NDF
   (2,592,000), the test checks bijection, monotonicity and that the label equals
   the plain base-nominal odometer.
5. **Sampled NDF.** The rates are `24000/1001`, `25`, `48`, `50`, `60`,
   `60000/1001` NDF, `120`, `120000/1001` NDF, `1` and `1000`. Each rate is checked
   at every minute boundary ±2 frames over 24 h, plus 10,000 seeded random frames.
6. **DF refusal.** DF is refused at `24/1`, `24000/1001`, `25`, `30/1`,
   `48000/1001`, `50`, `60/1`, `120/1` and `1000/1`, with reason
   `drop_frame_rate_unsupported`.
7. **Rate refusal.** `108930/4549`, `24/1001`, `2997/100`, `0`, `-24`, `True`,
   `"nan"` and `1001/1` are refused as `rate_unsupported` or `rate_invalid`.
8. **Range.** Frame `-1` and `frames_per_day` are refused, and the last frame label
   is `23:59:59;29` or `23:59:59:23`.
9. **Strict parse.** Dropped labels, wrong separator, `24:00:00:00`, `FF ≥ nominal`,
   wrong digit width and stray whitespace are refused with their typed reasons.
10. **Rational period.** `24/1` and `24000/1001` keep distinct periods for the same
    frame count, and no float appears in any conversion (a `Fraction` input
    round-trips).

### `tests/test_editor_marker_export.py` (≥ 14 tests)

Fixtures follow the `tests/test_editor_marker_plan.py` `inputs()`/`disk_fixture()`
shape: source hash `"a"*64`, uniform 24/1 PTS of 240 frames, clip 0–10 s,
markers including the label `recurrence, "uncertain" & <riff> ♫`, points and spans.

1. Uniform 24/1 FCPXML: parses with `xml.etree`, `version="1.10"`, has a DOCTYPE,
   uses rational `Ns`/`n/ds` times, and every marker `duration == frameDuration`.
2. No `completed` attribute exists anywhere; only ordinary `marker` elements appear.
3. A span becomes a START/END pair sharing the `marker_id` in both notes, and a
   point becomes a single marker.
4. Resolve ops: every `frameId` and `duration_frames` is `type(...) is int`, and
   `executable is False`, `api_contract == "unverified"`, `host_frame_id is None`.
5. The sidecar preserves the decimal lexeme `0.100000000000000001`, rational
   coordinates, quantization errors equal to the planner errors, and display labels.
6. Collisions: existing-marker and same-frame conflicts are excluded atomically
   per `marker_id`, kept in the sidecar and not shifted.
7. VFR PTS shaped like the real take (steps 24/25/26 at `1/600`, metadata
   `108930/4549` and `24/1`) writes no file and no directory, and reports
   `calibration_required`, `cadence: variable`.
8. No PTS gives `cadence: unknown` with zero files. Plan `calibration_required`
   (no grid) also propagates with zero files.
9. Uniform PTS at 1/25 with a 1/24 grid gives `grid_pts_period_mismatch`, and an
   offset grid origin gives `grid_origin_misaligned`.
10. DF at 24/1 is refused with `drop_frame_rate_unsupported`. A uniform
    `30000/1001` fixture with DF gives `tcFormat="DF"` and `;` labels.
11. XML escaping: Unicode, `&`, `<`, quotes and newlines round-trip unchanged
    through ElementTree, and `media_src_url` has its spaces and U+202F
    percent-encoded.
12. Determinism: two exports into fresh directories are byte-identical, and the
    stdout SHA-256 values match the files.
13. An existing `--output-dir` is refused without being modified. All fixture
    inputs are byte-identical before and after every test.
14. DTD: without `--dtd` the status is `not_performed`. With a synthetic minimal
    DTD written by the test, the status is `passed` and, for a mutated document,
    `failed`. A missing xmllint gives `unavailable` (an explicitly labelled skip).
    A synthetic DTD does not establish FCPXML 1.10 conformance.
15. More than 1,000 actions gives `selection_required` with zero files and no truncation.
16. The closed export profile rejects unknown keys, a bool `schema_version`, a
    `format` value outside the enum, an `fcpxml` block under `resolve_ops`, and a
    stale `plan_profile_sha256`.
17. An audio-only tail marker after the PTS extent stays in the sidecar as
    `outside_video_coverage`, `exported: false`.
18. The descriptor draft (`docs/agent-notes/sprints/20261006-s2/editor_export-tool-descriptor.json`)
    is a closed schema with `additionalProperties: false`, `format` enum
    `["fcpxml","resolve_ops"]` and `timeout_seconds` maximum ≤ 120.

The minimum across both modules is **≥ 24 tests**, above the DoD floor of 20.

## Completion metrics and claim classes

Claim classes are **M** (measured in a source fixture or a read-only real-take
measurement), **I** (inference from metadata or design), **U** (unverified,
recorded as such) and **L** (listening, which is never claimed here). Each metric
has an explicit denominator.

| # | Metric | Denominator | Class |
| --- | --- | --- | --- |
| 1 | DF frames passing bijection, monotonicity and reference-label checks | 2,589,408 + 5,178,816 + 10,357,632 = 18,125,856 frames | M |
| 2 | NDF exhaustive frames passing | 2,073,600 + 2,592,000 = 4,665,600 frames; sampled rates 10 × (1,440 × 5 + 10,000) | M |
| 3 | DF minutes with exactly k skipped labels, and tens-minutes with 0 | 1,296 + 144 = 1,440 minutes × 3 rates | M |
| 4 | Non-DF rates refused with `drop_frame_rate_unsupported` | 9 / 9 | M |
| 5 | Lane tests passing (labelled skips counted separately) | n / ≥ 24 | M |
| 6 | FCPXML fixtures with `version=1.10`, one-frame markers, 0 `completed`, pairs = 2 × spans | fixture files written | M (structure); U (app import) |
| 7 | Resolve operations with int `frameId`, `executable:false`, `api_contract:unverified` | operations emitted | M; U (API) |
| 8 | Sidecar rows carrying every required field, including non-exported rows | selected markers | M |
| 9 | Abstention arms writing zero files (VFR, no-PTS, period mismatch, origin, DF refusal, selection_required, nothing_exportable) | 7 / 7 fixture arms + 3 / 3 real-take arms | M |
| 10 | Real take reports `calibration_required` / `cadence: variable`, histogram compared with research | 1 take | M (PTS) / I (metadata hint) |
| 11 | Inputs byte-identical after runs (fixtures, mirror sources, accepted run, original take) | all hashed inputs | M |
| 12 | `application_import: not_performed`, `host_frame_id: null` | 2 / 2 formats; all rows | U, stated |
| 13 | Descriptor draft closed and timeout ≤ 120; skill draft present | 1 / 1 each | M (schema) |

The lane makes no claim of Final Cut or Resolve import, visible alignment, native
frame IDs, DTD conformance without a supplied DTD, musical correctness or
listening acceptance. Valid XML is not a successful import.

## Preregistration

**Not applicable.** This lane runs no experimental arms, scoring against truth,
tuning or model work. All behaviour is deterministic arithmetic or serialization
checked against closed-form references. The only real-data step, the real-take
acceptance check, has its expected outcome predeclared above before any
measurement, and its measured PTS histogram is recorded as found. Nothing is tuned
on the real take. If a real-take measurement contradicts the expected outcome, the
lane records the contradiction as a finding and changes no thresholds to match it.

## Root-owned changes the lane will request (phase 2, text only)

The phase 2 result will contain exact insertion text for:

- `program/tools.json`: the `editor_marker_export` descriptor. Inputs are
  `run_dir` (1–4096), `selection`, `profile` (1–1024) and `format` enum
  `fcpxml|resolve_ops`, with `timeout_seconds` an integer 1–120 defaulting to 120.
  `additionalProperties: false`, and there is no DTD, output path or argv
  passthrough. The output location is a root decision: the proposal is an exclusive
  `<run_dir>/editor-export/<format>-<plan_sha12>/`.
- `scripts/tool_api.py` and `scripts/mcp_server.py`: dispatcher entry and prompt
  for `.agents/skills/editor-marker-export/SKILL.md`.
- `just/workflow.just`: an optional `editor-marker-export` recipe.

## Timebox and handoff

- **Phase 1:** this spec, committed with `--no-gpg-sign`.
- **Phase 2:** timecode module and tests first, then the exporter, tests, contract,
  skill and descriptor drafts. Then the single real-take PTS scan and mirror check.
- **Phase 3:** the receipt JSON with test counts, hashes, the real-take outcome and
  the `root_owned_changes_requested` text.

If time runs short, the order of what is kept is: timecode plus property tests,
then abstention paths and the real-take `calibration_required` check, then the
uniform FCPXML/Resolve writers. A writer still pending at close is reported as
pending, not as done.

## Phase 2 status (appended 2026-10-06; frozen sections above unchanged)

- **Timecode:** `scripts/timecode.py` passed `tests/test_timecode.py` with
  11/11 tests. The suite checked 18,125,856 DF frames and 4,665,600 NDF frames
  exhaustively and covered 1,440 minutes × 3 DF rates for the skip property. On
  a host with load average 177–392, the suite took 1,410 s of wall time and
  85.7 s of user CPU, which exceeds the `timeout 600` wrapper's wall budget. It
  was therefore run under `timeout 2400`.
- **Exporter:** `scripts/editor_marker_export.py` passed 23/23 tests, with no
  skips because xmllint was present. The planner regression passed 21/21. Three
  additive conservative reasons are documented in `docs/spec/EDITOR_MARKER_EXPORT.md`:
  `asset_mapping_unknown`, `clip_bounds_off_grid` and `clip_outside_asset_extent`.
- **Real take:** the result matched the predeclared outcome, `calibration_required`
  / `cadence: variable` (`unknown` without PTS), with zero files in every arm and
  19/19 read-only inputs unchanged. The measured PTS histogram equals the
  research table. A finding: the predeclared compact selection binds to the
  arrangement markers, not to generic `markers.json`, so the build entrypoint
  refuses it, and the contract fallback `pure_make_plan` was used. Details are
  in `docs/agent-notes/sprints/20261006-s2/editor_export-real-take-receipt.json`.
- **Drafts:** the tool descriptor is
  `docs/agent-notes/sprints/20261006-s2/editor_export-tool-descriptor.json` and
  the skill is `.agents/skills/editor-marker-export/SKILL.md`. Root insertion
  text is listed in the lane result.
