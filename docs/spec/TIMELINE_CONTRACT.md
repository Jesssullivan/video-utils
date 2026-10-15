# Run manifest timeline contract

Authority: operator decision of 2026-10-15 (Linear TIN-6509), repository
AGENTS.md and R-N13. This contract is written before the code that enforces it.

Every run manifest has a `timeline` object. It says how output time relates to
source time. There are two mappings. Each verifier accepts exactly one.

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

`video-utils verify-run --timeline edl_v1 RUN_DIR` checks the hashes of every
listed output and recording, parses and validates the EDL with
`src/timeline.rs` (`edl_invalid` on failure), and cross-checks fps, frame totals,
clip names and shifts, and that every segment's source is a listed recording
(`edl_invalid` when they disagree). A `timeline.edl.sha256` that differs from the
file's `output_sha256` entry is `manifest_field_invalid`. It refuses an identity
manifest, with no mapping or `"identity"` (`timeline_mapping_mismatch`), and any
other mapping (`timeline_mapping_invalid`). Its receipt adds `timeline.mapping`,
`timeline.edl_sha256`, `timeline.total_frames` and `timeline.edl_segments`, plus
`manifest_kind`, the `sources` checks and `delivery`. `--timeline identity` is the
default path, named explicitly.

## What must not change

- The default `verify-run` receipt for an identity manifest stays
  byte-identical.
- Existing tamper tests pass unmodified.
- A refusal matrix test feeds a condense manifest to every guitar consumer of
  `no_time_stretch` and expects each to refuse.
