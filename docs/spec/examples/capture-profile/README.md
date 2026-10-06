# Capture-profile authoring example

[review.example.json](review.example.json) contains exactly the worker's 16 review keys. Every value is a placeholder; it contains no recording path, identity, authorization or acceptance. It is not an executable review. Substitute actual JSON types, including integer `schema_version: 1` and finite numeric start/end, then save the completed review beneath the verified run. Reusing placeholder authorization text does not establish existing authorization.

Bind three current byte hashes: original `INPUT` to `source_sha256`, `RUN_DIR/manifest.json` to `source_run_manifest_sha256`, and native `RUN_DIR/source.wav` to `source_pcm_sha256`. `INPUT` must be the exact original path in that manifest, rather than a same-content alias or denoised master. The manifest must already bind the source and native PCM, with `timeline.no_time_stretch: true`. The worker verifies native WAV headers, extent, rate and channels without decoding samples or rerunning decoder history.

`time_axis` is exactly `decoded_source_audio_samples`. Start/end are decoded-audio-relative seconds. With native sample rate `r`, the half-open sample interval is `[round(start_seconds*r), round(end_seconds*r))`; Python rounding matches the frozen media worker. It must lie inside `source.wav` with inclusive native duration 0.1–10 seconds. The same sample bounds must result from the review and CLI. Receipts retain requested seconds and separate `profile_seconds`; a one-ULP interval-scale start adjustment can bridge the frozen validator's boundary roundoff, with exact native bounds and end unchanged. Media spans add the manifest's verified `audio_start_seconds`; absent origin remains unknown. Source sample mapping uses neither a 16 kHz analysis export nor a rendered AAC clip.

Allowed review values:

- `review_status`: `reviewed_candidate`, `reviewed_possible_contamination`, `rejected_contaminated`.
- `authorization_scope`: `profile_authoring`, `experimental_capture_render`. The reference records existing scoped authorization; names and review judgments remain supplied assertions without identity authentication or a recurring confirmation prompt.
- `music_status` and `click_status`: `unknown`, `suspected`, `reviewed_no_obvious_content`, `reviewed_present`.
- `ambient_music_status`: `not_reported`, `suspected`, `reviewed_absent`, `reviewed_present`. Authoring never authorizes automatic ambient-music separation or classification as fan noise.

Rejected selection or reviewed-present music/clicks produces `needs_reselection` with no profile. Authoring-only scope produces `draft_authorization_incomplete` and a nonrunnable proposal. Existing render-scoped authorization produces `authored_unrendered` and a profile accepted by frozen `media.load_profile`; no DSP or learned noise shape occurs.

Pass values in an argument vector using this fixed CLI. The angle-bracket tokens are placeholders, not literal values or shell redirections:

```text
python scripts/capture_profile.py <ORIGINAL_INPUT>
  --run-dir <VERIFIED_RUN_DIR> --review <COMPLETED_REVIEW_JSON>
  --capture-start <START_SECONDS> --capture-end <END_SECONDS>
  --reduction-db <NR> --noise-floor-db <NF>
  --adaptivity <AD> --gain-smooth <INTEGER_GS>
  --integrated-lufs <LUFS> --true-peak-dbtp <DBTP>
  [--timeout-seconds <INTEGER_SECONDS>]
  [--eq <FREQUENCY_HZ> <GAIN_DB> <Q>]
  [--compressor-threshold-db <DB> --compressor-ratio <RATIO>
   --compressor-attack-ms <MS> --compressor-release-ms <MS>
   --compressor-knee-db <DB>]
```

All capture/DSP/loudness controls above are explicit; EQ/compression are absent by default. Repeated EQ has at most three bands. Compressor flags are all-or-none. Exact numeric/text/resource bounds are in the [workflow contract](../../CAPTURE_PROFILE_WORKFLOW_LANE.md). No arbitrary filters, arguments, URL, source hash override or inherited demo capture is supported.

Compact successful stdout fields are `schema_version`, `tool`, `status`, `evidence_kind`, `run_dir`, `output_dir`, `source_sha256`, nullable `profile_path`/`profile_sha256`/`proposal_path`, `receipt_path`/`receipt_sha256`, `capture` containing `requested_seconds`/`native_samples`/nullable `source_media_span_seconds`, and literal `dsp_performed: false`/`listening_accepted: false`. All three authoring/abstention states exit zero; structural/domain/I/O errors produce bounded error JSON and exit 2. The future typed application route is separate from direct structural validation and does not follow from this example.
