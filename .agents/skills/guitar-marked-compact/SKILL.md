---
name: guitar-marked-compact
description: Compose a compact marked guitar review movie by stream copy from a verified audio run and a verified arrangement-marker picture preview; verify exact packet, clock and PCM identity and never infer listening acceptance.
---

# Compose a compact marked review movie (copy only)

**Hook:** MCP tool `marked_compact`, prompt `guitar-marked-compact`. Direct worker: `python3 scripts/marked_compact.py RUN_DIR --picture-preview PREVIEW_DIR --arrangement-markers SELECTOR [--output DIR] [--timeout-seconds 600]`. Recipe: `just marked-compact RUN_DIR --picture-preview PREVIEW_DIR --arrangement-markers SELECTOR`. Read [the lane contract](../../../docs/spec/sprints/FULLER_S2.md) section 4.3.

## Intent and inputs

Combine one verified restoration run's delivery AAC (the audio branch, for example an accepted FULLER render) with the picture of a verified arrangement `marked_video` preview of the same original recording. No denoising, EQ, compression, normalization, picture encode or new analysis occurs; parents are read only.

- `run_dir`: verified run with `manifest.json`, `export/outcome.json` and `export/cleaned-video.mov`. Export proofs (source hash, frame count, relative start, DSP latency, true peak) must be true, packet translation exactly 0 and physical sync unverified.
- `picture_preview`: a `marked_video.py` output with status `marked_review_preview_verified_unreviewed` and marker mode `arrangement_reference_review`; its outputs and every recorded input hash must still match.
- `arrangement_markers`: the preview run-relative selector recorded by that preview; markers are rebuilt and must equal the preview bindings.
- `output`: optional fresh directory beneath `artifacts/` but not `artifacts/runs/`, not inside either parent; default `artifacts/experiments/marked-compact-<UTC>-<hex12>`.
- `timeout_seconds`: 1-600, default 600; two threads; owned process groups; no retry.

Both branches must share the original SHA-256 and native PCM rate/channels/sample count, with container/audio/picture origin 0 and no time stretch (`nonzero_origin_unsupported` otherwise). The AAC header extent must cover the preview's decoded picture extent.

## Evidence

Outputs: `marked-compact.mov`, `start.json`, parent/output packet tables, and `receipt.json` (`marked_compact_composition_verified`) or `failure.json` (`marked_compact_failed_preserving_parents` with `reason`). Checks are exact with zero tolerance: ordered video packet payload hashes and rational PTS/DTS/duration; AAC payload, timing and skip/discard side data; decoded AAC `pcm_f32le` SHA-256; picture and AAC format keys and extradata hashes; composed origins; unchanged AAC header extent; all parent hashes before and after.

Typed refusals: `run_dir_invalid`, `export_unverified`, `preview_unverified`, `arrangement_markers_mismatch`, `source_mismatch`, `native_pcm_mismatch`, `nonzero_origin_unsupported`, `audio_does_not_cover_picture`, `output_invalid`, `input_changed`, `packet_identity_failed`, `pcm_identity_failed`, `format_identity_failed`, `deadline_exceeded`, `ffmpeg_failed`, `internal_error`.

## Claims and limits

`chain_identity` classifies the audio branch as `identical_accepted_fuller_v1`, `fuller_v1_template_other_binding` or `not_fuller_v1`. `listening_acceptance` is `accepted_fuller_v1_by_operator_2026-10-06` only for the identical chain with byte-identical `cleaned.wav` (and export video); everything else is `not_performed`. The composite itself has no visual or listening review. `markers_are_analysis_of_audio_branch` is true only when the preview analyzed the run's own `denoised.wav`; otherwise the labels describe a different signal version of the same take. Receipts always carry the unknown/abstain fields (capture noise-only false, music/click unknown, physical sync false, no 32 Hz restoration claim, no per-passage level match, no performance or note-correctness verdict, no master/latest/default change, no native editor import). Arrangement labels stay review prompts against operator intent, never missed-note or mistake verdicts.

## Iterate

Inspect `failure.json` reasons before rerunning; a fresh output is required each time. Rebuild stale markers or previews through their owning tools rather than editing them. Visual review of the composite and listening remain separate operator steps.
