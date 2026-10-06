---
name: guitar-capture-profile
description: Author fresh source-bound guitar restoration settings from verified native metadata and an explicit capture review, preserving authorization scope and contamination uncertainty without rendering or accepting audio.
---

# Author a source-bound capture profile

**Hook:** MCP tool `capture_profile`, prompt `guitar-capture-profile`. Inspect `tools/list` for current availability and schema. The admitted authoring worker validates existing evidence and writes settings/receipts. It performs no DSP, new audio decode, learned noise shape, separation, audible master or listening acceptance.

## Use and closed controls

Required local paths `input`, `run_dir` and `review` are 1–4,096 characters. Input is the current original; run is beneath repository `artifacts/runs/`; the regular review file is inside that verified run. Reject traversal/symlink components. Required finite `capture_start_seconds`/`capture_end_seconds` are audio-relative, within native extent; duration is 0.1–10 seconds. No old take's source hash can replace the freshly computed current identity.

Required explicit controls have no numeric defaults:

| Field | Inclusive range |
|---|---|
| `reduction_db` | 0.01–12 |
| `noise_floor_db` | −80 to −20 |
| `adaptivity` | 0–1 |
| `gain_smooth` | Integer 0–50 |
| `integrated_lufs` | −70 to −5 |
| `true_peak_dbtp` | −9 to 0 |

Optional `peaking_eq` has at most three exact bands: `frequency_hz` 160–6,000 and strictly below native Nyquist, `gain_db` −3 to +3, `q` 0.5–2. Optional `compressor` has all five exact fields: `threshold_db` −36 to −6, `ratio` 1–3, `attack_ms` 8–20, `release_ms` 60–200, `knee_db` 0–6. Omitted EQ/compression means none. Compressor wet fraction is fixed at 25%, with no makeup gain. Unknown keys, booleans as numbers, nonfinite values and partial stages reject. Shared `timeout_seconds` is integer 1–60/default 60. No arbitrary filter, full profile object, executable, URL, source-hash override or inferred optimum is exposed.

Direct worker uses `python3 scripts/capture_profile.py "<original>" --run-dir "<run>" --review "<review.json>" --capture-start <seconds> --capture-end <seconds> --reduction-db <value> --noise-floor-db <value> --adaptivity <value> --gain-smooth <integer> --integrated-lufs <value> --true-peak-dbtp <value>`. Fixed optional EQ/compressor flags are documented in [the workflow](../../../docs/spec/CAPTURE_PROFILE_WORKFLOW_LANE.md). Recipe `just tool-run capture_profile '<arguments-json>'` uses the same typed fields; inspect [the hook contract](../../../docs/spec/CAPTURE_PROFILE_TOOL_CONTRACT.md).

## Source and review evidence

Verify current original, source-run manifest and native `source.wav` hashes, PCM header/rate/channels/count, no-time-stretch mapping, context and review receipts. Hashing reads source/PCM bytes; header inspection seeks over PCM payload without decoding it. Original-to-PCM decoder history is retained from the baseline, not independently rerun. Capture seconds round to native samples and must match the review's exact sample mapping. Receipts separate requested seconds, exact native bounds and profile seconds; a boundary-only floating-point encoding adjustment never moves a native sample. Unknown audio origin leaves source-media span null; never invent zero origin.

The version-1 review sidecar has exactly sixteen fields: schema, three source/manifest/PCM hashes, start/end, fixed `decoded_source_audio_samples` time axis, selected/reviewed identities, review state, authorization scope/reference, music/click/ambient states and note. Identities, selection, listening and authorization are supplied assertions, not authenticated facts. Current session authorization persists: record existing capture-render authority faithfully and do not ask again merely to populate a review field. Do not invent a review or promote authoring-only scope into render authority.

## Interpret all three outcomes

Read the nested worker status and nullable paths, not just successful dispatch:

- `authored_unrendered`: existing `experimental_capture_render` scope permits a fresh valid source-bound `profile.json` plus receipt. No render or noise shape was produced.
- `draft_authorization_incomplete`: `profile_authoring` scope produces nonrunnable `proposal.json`; capture-authorized render permission is not added.
- `needs_reselection`: rejected contamination or reviewed-present capture music/clicks produces a receipt without runnable profile or proposal. Do not weaken the review to make it pass.

Outputs are immutable `capture-profiles/<id>/` descendants. Runtime bounds are 60 seconds, original <=3 GiB, native PCM <=1 GiB, 8–192 kHz/1–2 channels/<=600 seconds, manifest <=1 MiB, contexts/receipt <=64 KiB and review/profile/result <=16 KiB. Changed inputs, stale hashes, malformed headers and exceeded limits reject.

## Research and bounded iteration

Unknown/suspected fan, guitar sustain or click overlap stays uncertain; quiet intervals and similar tuning do not prove noise-only capture or transferable shape. Near-32 Hz nine-string content, harmonics, legato and artist/articulation references are musical context, not automatic EQ or score targets. Absolute floor/reduction controls are not measured SNR. Ambient-music uncertainty receives a warning; authoring does not authorize automatic separation.

Inspect and research the capture/control intent through [restoration refinement](../../../docs/spec/RESTORATION_REFINEMENT_LANE.md), change one supported setting in a fresh candidate, and retain source/review/settings/context hashes. Authoring does not extend the existing fixed denoise enum; subsequent custom-profile application needs its separately admitted route and faithful existing scope. Later comparisons distinguish bypass, pure denoised/residue, optional processed EQ/compression and final normalization. Pure residue cannot certify later-stage fidelity; no best tone or preserved attacks is established by a valid profile. Follow [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for durable evidence and acceptance boundaries.
