---
name: media-share-export
description: Create a smaller lossy guitar sharing MP4 with bounded resolution, video quality and AAC bitrate controls, retaining source-clock checks and fresh derivative receipts without overwriting or accepting the master.
---

# Export a compact sharing derivative

**Hook:** MCP tool `share_export`, prompt `media-share-export`. The experimental typed route is integrated locally; inspect `tools/list` for current schema. Read [the sharing worker contract](../../../docs/spec/SHARE_EXPORT.md) for checks and primary-source references, and [the skill receipt](../../../docs/agent-notes/2026-10-06-share-export-skill.md) for evidence checkpoints. Generated qualification covers mono/stereo fixtures; permitted channel bounds are not proof of every receiver's compatibility. Local source/prompt qualification is separate from publication, actual-take quality and listening acceptance. This operation compresses an existing video for sharing; it does not restore audio, create annotations or select a master.

## Choose supported controls

Required `source` and `output` are literal local paths, 1–4,096 characters. Source is an existing regular file with video and audio. Output is a fresh `.mp4` with a fresh adjacent `.mp4.receipt.json`; its parent must already exist. Typed preflight rejects input/output aliases, traversal and symlink components before normalization. Direct CLI rejects leaf symlinks but normalizes ancestor paths; use canonical paths for the stricter MCP route rather than assuming `/tmp` aliases are accepted. Source may be an existing marked preview or approved delivery; never overwrite it or a master/latest pointer.

| Field | Values / default |
|---|---|
| `height` | Even integer 240–1080; default 720 |
| `crf` | Integer 18–32; default 27 |
| `audio_kbps` | Integer 64–192; default 96 |
| `codec` | `h264` (default), `hevc`, `copy` |
| `timeout_seconds` | Integer 30–900; default 900 |

H.264 software encoding uses fixed veryfast preset, `yuv420p` and CRF27 by default. HEVC is opt-in, using veryfast/`hvc1`/`yuv420p`; do not assume it will finish faster or guarantee a smaller useful file. Resize within requested height while retaining aspect ratio approximately through an even width, without upscaling. Video copy does not resize or apply CRF: input height must already fit the requested limit and codec must be H.264 or HEVC, otherwise it rejects. Copy refers to video packets; audio still becomes the sharing AAC track. Non-square pixels or video side-data/rotation require an explicit supported upstream export rather than silently fitting an ambiguous display transform.

AAC at 96 kbps is intentionally lossy, preserving source audio rate/channels. Smaller resolution, higher CRF and lower audio bitrate generally reduce size but can soften callouts, blur fast movement or damage distorted-guitar texture and attacks. No supported knob guarantees globally minimum file size, a specific byte budget, identical picture/audio or transparent quality. Choose a useful size/quality compromise for the recipient; do not describe a derivative as a new native master.

An already efficient source can grow. Read actual output bytes and measured reduction rather than treating every verified export as a size improvement.

Direct route:

```text
python3 scripts/share_export.py SOURCE OUTPUT --height 720 --crf 27
  --audio-kbps 96 --codec h264 --timeout-seconds 900
```

No arbitrary filter/argv, encoder preset, FPS, sync offset, model/runtime, install, upload or overwrite field is exposed. Required FFmpeg/ffprobe and chosen encoder must already be available. The public timeout is passed unchanged: the worker reserves ten seconds, giving 20–890 operation seconds, exceptional cleanup up to five seconds and reporting margin. This is one overall job budget, not a fresh deadline per stage or a hard real-time guarantee.

## Inspect measured evidence

Source bounds are 3 GiB/300 seconds, native audio 8–192 kHz/1–8 channels. Preserve source frame clock and variable frame timing, aspect ratio and audio origin; reducing height does not authorize frame-rate conversion, implicit downmix or an invented sync correction. Reencoding picture changes pixels; AAC changes samples. Timing/native rate/channel checks must not become bit-identity or physical capture synchronization claims.

Inspect the actual output bytes and SHA, source identity, codec/dimensions, video packet presentation timing/count, duration, native audio rate/channels and measured decoded output peak or explicit silence. The worker encodes video once and permits at most two audio-only peak attempts toward <=−1.5 dBTP, with attenuation bounded to 3 dB; evidence must describe what passed rather than infer success from an exit code. AAC timing/sample extent includes recorded priming/padding allowance, not exact sample identity. Video-copy proof is scoped to retained video packet evidence, not AAC/source-audio equality. Read bounded outcome/error receipts and nullable output paths before retrying; a failed call cannot establish that no derivative exists.

Successful `exported_unreviewed` is a fresh sharing candidate, with listening/master adoption false. Source/master/latest and prior outputs remain intact. Runtime/source/timing/peak verification is separate from visual legibility, musician listening, receiving-player compatibility, approved master selection and publication/upload.

Read domain status and MCP `isError` independently of transport success. `rejected` or `failed_no_export_published` does not publish this worker's export. `exported_unreviewed_reporting_interrupted` can retain published `output` even when adjacent-receipt/report publication failed. `publication_outcome_unknown` retains prepared `possible_output`, not proof that it exists. Verify the exact output/receipt SHA and retained staging/failure receipts before retrying or declaring absence; do not replace a committed derivative. Missing stdout or a timed-out client leaves outcome unknown until inspection. Failure receipt preservation can itself fail; absence of a diagnostic is not cleanup or publication proof.

`diagnostic_fields_omitted` lists compact transport projections when present; full details remain in the hash-bound failure receipt. Follow that evidence rather than inventing omitted selectors or treating them as absent artifacts. Transport can succeed while the hook correctly reports a domain error.

Output/source are bounded to 3 GiB, video packet/frame evidence to 100,000 entries, compact/domain JSON to 16 KiB and durable receipts to 64 KiB. Retained stage progress can identify the last frame/out-time; it is progress, not completion or preserved quality. Owned subprocess logs are bounded, and recorded-session cleanup is not proof about every escaped descendant.

## Research and iterate

Inspect source dimensions and existing annotation visibility first. Compare one supported resolution/CRF/audio-bitrate change in a fresh output; retain settings, command, versions, actual bytes, hashes and verification receipts. Copy is useful only when existing dimensions already fit and compression savings from AAC meet the sharing goal.

Review quiet/active distorted nine-string passages, near-32 Hz low register, palm-mute attacks, fast sweeps/legato and sustained tails. Lossy codec changes can alter texture and clarity even when peak/timing checks pass. Read small callouts at target resolution and actually test the intended player when compatibility matters. Research the chosen codec/muxer behavior through the worker's primary-source FFmpeg references; use supported knobs rather than inventing filters. Keep retained source, restoration/master acceptance and sharing-derivative acceptance distinct.
