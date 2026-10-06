---
name: guitar-tone-ab
description: Attribute low-end and thin/nasal balance changes to restoration stages of a distorted nine-string take at matched loudness, and hand the operator blind level-matched excerpt pairs, without claiming perception, room response or note identity.
---

# Compare stage files at matched level before judging tone

**Hook (draft):** MCP tool `tone_ab` and prompt `guitar-tone-ab` once root registers the descriptor; until then use the direct worker `python3 scripts/tone_ab.py run --run-dir <run> --common-region-start 5.0 --common-region-end <end> [--candidate-run-dir <run2>] [--timeout-seconds 1200]`. `python3 scripts/tone_ab.py describe` prints the typed descriptor draft. Read [the frozen contract and preregistration](../../../docs/spec/sprints/TONE_S2.md) before a run.

**Capability:** experimental, measurement-only. Output is a fresh directory under `artifacts/s2/tone_ab/<run_id>-<UTC>/` with `tone-ab.json`, `attack-positions.json`, one `trial-lowshelf.wav` and six blind excerpt files. The worker refuses to write inside the run directory, a candidate run directory or any `artifacts/runs/*` path, and fails if any protected file's sha256, size or mtime changes.

## Inputs and refusals

The closed schema has `run_dir`, optional `candidate_run_dir`, `common_region_start`, `common_region_end` and `timeout_seconds` (1–1800, default 1200). Unknown fields, booleans as numbers, NaN/inf, a start before 5.0 s (the setup guitar/amp and windup interval), an end at or before the start or past the run duration, and a region shorter than 45 s are refused. Each stage file must match `manifest.output_sha256` (`stage_hash_mismatch`) and the manifest's native rate/channels/frame count from a stdlib RIFF read plus an FFprobe cross-check (`native_extent_mismatch`). A candidate must share the source sha256 (`candidate_source_mismatch`) and is flagged `denoise_basis_differs_confounded` when its pure denoise differs.

## What it measures

Arms are `source`, `pure_denoise`, `tone_dynamics_pre_gain` (EQ and compressor combined, when the manifest lists `processed.wav`), `delivery_master` and the single preregistered `trial_lowshelf` (`lowshelf=f=100:t=q:w=0.7:g=1.5:r=f64` on the master, f32, separate deletable file). Integrated LUFS uses FFmpeg loudnorm `input_i` over the region; every arm gets one static gain toward the quietest arm (all gains ≤ 0 dB), with up to three corrections and `match_lu_delta ≤ 0.3` LU required for `matched`. Six bands (20–45, 45–90, 90–160, 160–400, 400–2000, 2000–8000 Hz) use a 16384-point periodic-Hann Welch estimate at native rate, reported raw, matched and as a share of the six-band sum. Attack panels take positions from an `analysis.json` bound to the run's denoised sha256 (run dir, then the capture-profile parent run) and report 20 ms mean-square energy and magnitude-weighted centroid with events/in-region/used denominators.

## Guitar-specific interpretation

The instrument is the nine-string C1 F1 Bb1 Eb2 Bb2 Eb3 Ab3 C4 F4 tuning with C1 near 32.7 Hz. A 20–45 Hz level is mixture energy, including fan and room, not a measured played C1. Stage deltas are mixture-energy changes; `fan_only_gain` and `music_only_gain` stay null. Distortion moves energy into harmonics, so a mid-band share change is not a nasal-quality verdict. Attack positions may be clicks, picks or noise (`attack_identity: unverified`); never derive missed or extra notes from them.

**Review scenario:** the trial adds about +1.4 dB raw at 20–45 Hz. That is the expected filter effect, recorded as `rejected_or_unreviewed_trial` with `adopted: false`; it is not evidence of fuller perceived tone, a recovered fundamental or room response, and the 160 Hz EQ floor stays until root and the operator decide.

## Agent iteration

Run once per fixed region; do not retune the shelf, bands, tolerance, excerpt rule or region after seeing numbers, and do not try a second shelf. Hand the operator the X/Y excerpt files before revealing `excerpts.blind_key`; `operator_preference`, `perceived_fullness` and `nasal_quality` stay null until they answer, and `claims.listening` stays empty. A failed match or a negligible change is a valid recorded result. Save dated receipts in `docs/agent-notes/` with the script sha256, spec commit, input hashes and metrics against their denominators, citing R-N13. Never download a model, overwrite a master, change a profile or adopt a default from this tool.
