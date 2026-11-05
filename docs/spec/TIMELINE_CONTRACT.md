# Run manifest timeline contract

Authority: operator decision of 2026-10-15 (Linear TIN-6509), repository
AGENTS.md and R-N13. This contract is written before the code that enforces it.

Every run manifest has a `timeline` object. It says how output time relates to
source time. Three mappings have verifiers (`identity`, `edl_v1` and
`narration_v1`), and each verifier accepts exactly one. Every guitar verifier
refuses the three narrated-video mappings below.

## `identity`: guitar takes

This is today's contract, unchanged.

- `timeline.no_time_stretch` must be JSON `true`.
- `timeline.mapping` is optional. When present it must be the string
  `"identity"`. Every manifest written before this contract omits it.
- `video-utils verify-run RUN_DIR` refuses a manifest whose `timeline.mapping`
  is present and not `"identity"`, with the existing reason
  `time_stretch_not_excluded`. A `null` or non-string mapping is refused the same
  way. The check runs right after `schema_version`, so a condense manifest gets
  this reason rather than a missing-field one.
- Every Python consumer keeps its `no_time_stretch is True` check.

## `edl_v1`: condense runs

A condense run maps output time to source time through an EDL.

- `timeline.mapping` is `"edl_v1"` and `timeline.no_time_stretch` is JSON
  `false`. An absent or `true` value is refused (`timeline_mapping_invalid`).
- `timeline.edl` names the EDL file and its SHA-256. The file is listed in
  `output_sha256` with the same digest.
- `timeline.fps` and `timeline.total_frames` match the EDL and the delivered
  video's frame count.
- `timeline.clips` lists each clip's name and `shift_seconds`. The source axis
  is per-clip analysis seconds from the first decoded audio sample; the source
  time is the analysis time plus the clip's shift. The output axis is the
  delivered frame index divided by `fps`.
- The manifest has `kind: "condense_edit"` and a `sources` list. It has no
  top-level `source` or `pcm` block, so no guitar reader can half-read it.
- Condense manifests live under `artifacts/condense/<run_id>/`, outside
  `artifacts/runs/`.

- `sources` lists 1 to 64 recordings, each `{clip, path, sha256}` with a unique
  clip name. `delivery` names the delivered file, which is listed in
  `output_sha256`, and its `video_frames`.
- `uploads`, when present, lists at most 8 upload copies, each `{file, of,
  video_frames, faststart, moov_offset, mdat_offset, ...}`. Every listed
  `*.upload.mp4` output is described; `file` and `of` are listed outputs;
  `video_frames` equals `delivery.video_frames` (`upload_invalid`); `faststart`
  is true and `moov_offset` precedes `mdat_offset` (`upload_not_faststart`).
  Other fields are open (docs/spec/CONDENSE.md).

`video-utils verify-run --timeline edl_v1 RUN_DIR` checks the hashes of every
listed output and recording, parses and validates the EDL with
`src/timeline.rs` (`edl_invalid` on failure), and cross-checks fps, frame totals,
clip names and shifts, and that every segment's source is a listed recording
(`edl_invalid` when they disagree). For each upload copy it then reads the
top-level ISO BMFF box headers, no media data: the first `moov` must precede the
first `mdat` (`upload_not_faststart`) at the manifest's offsets, and no box may
overrun the file (`upload_invalid`). A `timeline.edl.sha256` that differs from the
file's `output_sha256` entry is `manifest_field_invalid`. It refuses an identity
manifest, with no mapping or `"identity"` (`timeline_mapping_mismatch`), and any
other mapping (`timeline_mapping_invalid`). Its receipt adds `timeline.mapping`,
`timeline.edl_sha256`, `timeline.total_frames` and `timeline.edl_segments`, plus
`manifest_kind`, the `sources` checks, `delivery` and `uploads`. `--timeline identity` is the
default path, named explicitly.

## `narration_v1`: narration runs

Amendment proposed with the narrate CLI (TIN-7087; docs/spec/NARRATE.md). A
narration run lays a new track on an output clock. It maps no source media, and
no source media is ever time-stretched. Segments of the narration audio may be
sped up by the engine's speed knob or FFmpeg `atempo` to fit a target duration.
A voice's `tempo` (`Voice.dhall`) also changes every take's tempo with FFmpeg
`atempo` before QA and the fit. Each EDL row records it as `voice_tempo`, and
`stretch_applied` describes the fit alone.

- `timeline.mapping` is `"narration_v1"` and `timeline.no_time_stretch` is JSON
  `false` in every narration manifest, including a render whose segments needed
  no fit at all (`timeline.stretch_applied: false`). Guitar consumers check only
  `no_time_stretch is True`, so the flag alone keeps them out, and the mapping
  is never absent, `null` or `"identity"`.
- `timeline.edl` names `narration.edl.json` and its SHA-256, listed in
  `output_sha256` with the same digest. The narration EDL has `kind:
  "narration_edl"`, `sample_rate`, `total_samples` (equal to the delivered
  WAV's) and one row per segment: its output start and end, target start and
  duration when the input carried them, natural length, engine speed, `atempo`
  factor, padding, late start and overrun.
- The manifest has `kind: "narration_render"` and `synthetic: true`. It has no
  top-level `source` or `pcm` block.
- Narration manifests live under `artifacts/narrate/<run_id>/`, outside
  `artifacts/runs/`.
- `python -m narrate verify RUN_DIR` (`narrate/verify.py`) checks them: the
  mapping and flag, every listed hash, no unlisted file, the IR digest, the
  EDL against the WAV, and the manifest's content digest. `video-utils
  verify-run` refuses a narration manifest on both paths: by default and with
  `--timeline identity` (`time_stretch_not_excluded`), and with `--timeline
  edl_v1` (`timeline_mapping_invalid`).
- The refusal matrix test runs every guitar consumer case again with a
  narration manifest whose `stretch_applied` is false
  (`tests/test_timeline_contract.py`, the `Narration*` classes), and
  `tests/cli.rs` asserts both `verify-run` refusals.

## Narrated-video mappings: `narrated_video_v1`, `avatar_overlay_v1`, `music_bed_v1`

Amendment proposed with the narrated-video types (TIN-7476, lane L2;
docs/spec/NARRATED_VIDEO.md). A narrated-video job lays narration, kitpip
overlays and a music bed on a base picture's clock. Each stage writes its own
manifest, with `kind: "nv_stage"` and the stage's name. No stage time-stretches
source media. A stage manifest that carries narration audio, an overlay or a bed
uses one of three mappings, and none of them is identity:

| Mapping | Stages | Output axis | Extra timeline field |
| --- | --- | --- | --- |
| `narrated_video_v1` | `place`, `mix`, `compose`, `handoff` | base frame index / fps, and sample index / sample rate, on the base clock | `placements`: `placements.json` and its SHA-256 |
| `avatar_overlay_v1` | `avatar` | overlay frame index / fps on its segment's narration clock. Compose places frame 0 at the segment anchor | `narration`: the narrate run id and its content digest |
| `music_bed_v1` | `music` | bed sample index / sample rate | `layers`: each loop's SHA-256 and `tempo_factor` |

- `timeline.no_time_stretch` is JSON `false` in every one of them. That holds
  for a stage that changed no tempo too (`timeline.stretch_applied: false`), as
  for `narration_v1`. In `music_bed_v1`, `stretch_applied` is true when any
  layer's `tempo_factor` differs from 1. `timeline.output_axis` and
  `timeline.source_axis` name the clocks, and the source axis is always "none".
- The manifest has `kind: "nv_stage"`, and `synthetic: true` whenever any input
  is synthetic. It has no top-level `source` or `pcm` block.
- These manifests live under `artifacts/narrated/<job_id>/`, outside
  `artifacts/runs/` and outside every narrate run directory.
- `video-utils verify-run` refuses each mapping on both paths: by default and
  with `--timeline identity` (`time_stretch_not_excluded`), and with `--timeline
  edl_v1` (`timeline_mapping_invalid`). The stage store gets its own verifier in
  lane L3 (`python -m narrate video verify`).
- One fixture per mapping, `narrate/tests/fixtures/narrated-video/<mapping>.json`,
  fixes the timeline shape the stages must write. `tests/test_timeline_contract.py`
  runs every guitar consumer case once per mapping (the `NarratedVideo_*`
  classes), and `tests/cli.rs` asserts both `verify-run` refusals for each. The
  lane that first writes a mapping adds a shape test against its fixture, as
  `narrate/tests/test_contract_shape.py` does for `narration_v1`.

## What must not change

- The default `verify-run` receipt for an identity manifest stays
  byte-identical.
- Existing tamper tests pass unmodified.
- A refusal matrix test feeds a condense manifest, a narration manifest
  with zero applied stretch, and a stage manifest for each narrated-video
  mapping to every guitar consumer of `no_time_stretch` and expects each to
  refuse.
