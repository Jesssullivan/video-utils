# Changelog

## Unreleased

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
