# Changelog

## Unreleased

### Added

- `src/timeline.rs` and `video-utils timeline validate|table|map|quantise`: the
  EDL model, frame quantisation and time map, bit-exact with the frozen
  talk-condense oracle (`tests/fixtures/edl-golden-v1.json`).
- `video-utils verify-run --timeline edl_v1`: condense runs are verified against
  their hash-bound EDL. The default receipt for guitar runs is unchanged.
- `condense publish`: a hash-bound run under `artifacts/condense/<run_id>/`.
- MCP tools 47 to 57: `timeline_validate`, `timeline_map` and the nine condense
  stages, each with a skill.

### Changed

- The condense edl stage validates every `edl.json` with the Rust timeline.
- Condense defaults: 2 parallel jobs, 4 whisper threads and a 7200 s limit per
  tool call (`CONDENSE_TOOL_TIMEOUT_S`).
- Narrated video: J168 removes the `ip_private` and BS-21 refusals for go-live,
  and the November 30, 2026 audit revisits them. `ip_private` needs no denylist,
  number and geometry entries and the `script` class stop matching, and
  `nv subject` stops refusing `shown_text_unread`. `never_name` is unchanged.

## 0.2.0 (2026-10-15)

### Added

- `condense/`: talk condensing, moved from `Jesssullivan/talk-condense` at commit
  `bf5b9dc` (`docs/spec/CONDENSE.md`).

### Migration from talk-condense

- The package is `condense` instead of `talk_condense`. Every module is
  byte-identical; the tests change only their import lines.
- Recipes are `just condense-<stage>` from the repository root instead of
  `just <stage>`. Run them inside `nix develop .#condense`.
- The whisper model is the registered `ggerganov-whisper-cpp-ggml-small.en`
  entry in `program/models.json`. `just condense-model` fetches it into
  `models/`; the dev shell does not download it.
- The flake keeps talk-condense's nixpkgs revision for this shell: FFmpeg 8.1.2
  and whisper-cpp 1.8.4. `ffmpeg-headless` replaces `ffmpeg-full`; it has every
  filter and encoder the stages use.
- talk-condense had no licence file. Its sole author contributes it under this
  repository's MIT licence.
