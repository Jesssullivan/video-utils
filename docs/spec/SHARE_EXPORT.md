# Bounded sharing export

This separate delivery stage produces a fresh MP4 for sharing, keeping the
restored master and original intact. Source qualification and generated-fixture
proof are separate from an actual-take export or listening acceptance.

CLI: `python scripts/share_export.py SOURCE OUTPUT.mp4 --codec h264 --height 720
--crf 27 --audio-kbps 96 --timeout-seconds 900`. The Python API is
`share_export(source, output, *, height=720, crf=27, audio_kbps=96,
codec='h264', timeout_seconds=900)`.

Controls are closed: even height 240–1080; CRF 18–32; AAC 64–192 kb/s; codec
`hevc`, `h264`, or `copy`; total timeout 30–900 seconds. H.264 is the default after both actual demo HEVC medium and veryfast renders
hit their 500-second encode cap; this is a measured local delivery constraint,
not a universal hardware comparison. Optional HEVC uses libx265
veryfast, hvc1 and yuv420p. H.264 uses libx264 veryfast/yuv420p. Height is a
maximum: square-pixel aspect ratio is retained approximately through an even
width, with no upscaling. Copy accepts only H.264/HEVC already within the height
bound and preserves coded video. Existing video stream side-data and nonsquare
pixels require an explicit upstream export; no implicit rotation or HDR policy.
CRF is unused for copy and remains recorded for reproducibility.

Source and output are local normalized paths of 1–4096 characters; leaf symlinks
are rejected and ancestor paths resolve normally. The source is a nonempty
regular file no larger than 3 GiB with audio and video, duration at most 300
seconds, native audio 8–192 kHz and 1–8 channels. Output must have an existing
parent and fresh `.mp4` filename; its `.mp4.receipt.json` sidecar must also be
fresh. No input alias, overwrite, original/master adoption or latest update.

The total deadline reserves ten seconds: operation `timeout_seconds−10`, owned
exceptional cleanup at most five seconds, and five seconds for diagnostics.
All subprocess stages share the operation deadline. The qualified application
runner owns fresh child sessions, validates live SID/PGID before signals and
reaps direct children. Inspection uncertainty remains a failure, never proof of
absence. Two numeric threads constrain FFmpeg and each encoder; x265 also has
closed `pools=none:frame-threads=2` controls. No external executable selection beyond the
existing FFMPEG/FFPROBE environment convention and PATH resolution.

Video is encoded once to a retained intermediate. AAC is encoded separately at
native rate/channels, measured using decoded FFmpeg loudnorm input statistics,
and if measured true peak exceeds −1.5 dBTP, reencoded once from the source with
only negative volume compensation (at most 3 dB, 0.10 dB safety margin). Video
is reused; there are at most two audio encoding attempts. Final MP4 uses stream
copy and faststart. This is intentional lossy delivery, not another restoration
or remaster. Measurements have FFmpeg's reported precision; no listening claim.

Verification hashes the source before and after, compares video packet count,
sorted presentation timestamps and final tail extent with rational time bases,
and bounds differences by a mux tick. Every duration must be a positive integer.
Copy additionally checks every packet duration, coded payload hashes and decode
timestamps. Intermediate coded packet durations can differ after encoding:
the generated 41-packet VFR fixture retained every PTS and exact two-second tail
while eight intermediate durations changed; adjacent presentation timestamps
define display intervals independently of coded packet reordering. Changed encoder DTS are not expected to match.

Edit-list pre-roll (S2 share_export_fix, 2026-10-06): MOV/MP4 sources cut by
stream copy can begin with decode-only packets outside the edit list; FFmpeg's
demuxer flags them `D` (ffprobe `flags`) and the decoder never presents them.
The accepted run export `artifacts/runs/20261006T041633Z-990aa1bd6737/export/cleaned-video.mov`
has 3,631 video packets, of which 10 leading packets (one keyframe GOP head;
time base 1/19200; first PTS −14368 = −0.7483 s, last PTS −800 ≈ −0.0417 s,
whose 800-tick duration ends at 0) are decode-only, and 3,621 are presented
from PTS 0 to 150.885 s.
A re-encode correctly emits no frame for those 10, so the former total-count
comparison refused this valid input with "video packet count changed". Packet
probes now include `flags`. Re-encodes compare presented packets on both sides
(`comparison_scope=presented_packets_excluding_edit_list_discard`), refuse any
decode-only packet in the re-encoded output, and still refuse any dropped,
duplicated, shifted or tail-changed presented picture; copy
compares every coded packet (`all_coded_packets`), including identical
decode-only state, payload hashes and DTS. Receipts record total, presented and
decode-only counts. A count refusal remains `validation_failed` and names the
scope and both presented/decode-only counts; it is never a reason to retry with
copy or different settings. Absent flags are treated as presented (strict).

Valid inputs (measured vs not): the run-directory `export/cleaned-video.mov`
above exported with default H.264 720p CRF27 on 2026-10-06 (3,621/3,621
presented PTS identical, tail delta 0, 3,621 decoded output frames, 427.65 s
wall, 22,555,377 bytes, SHA256 `2eba932a…`; evidence in
`docs/agent-notes/sprints/20261006-s2/share_export_fix-handoff.json`). The Desktop
export used `copy` on an already-encoded 720p H.264 parent without pre-roll.
Direct H.264 export of the accepted marked movie (its recorded parent: 3,621 packets from PTS 0)
is expected to pass the same comparison but was not run by this lane. Inputs
with multiple edits or interior decode-only packets are compared on presented
packets too, without actual-take qualification.
This packet evidence does not prove source decoded-frame identity or physical
capture synchronization. The bounded delivery output is fully decoded with
error checking. Audio decoded-frame clocks, samples, native rate/channels and
endpoints are checked, with one AAC frame plus mux tick endpoint allowance and
2048 total decoded padding samples. Exact PCM identity is intentionally absent.
Encoded peak is checked again after muxing. File reduction is measured, not
guaranteed; a source already efficiently compressed may grow.

Atomic hard-link creation publishes a fresh output without clobbering a race.
The sidecar follows; committed output remains recoverable if sidecar/reporting
is interrupted. Failure receipts retain staged media, bounded logs and latest
FFmpeg progress (`frame`, `out_time`, `speed`), distinguishing rejected input,
no published export, committed unreviewed reporting interruption and uncertain
publication. No committed candidate is deleted automatically. JSON result is
at most 16 KiB; durable receipts at most 64 KiB; subprocess stdout/stderr are
monitored at 4 MiB each and retained tails are truncated to that exact cap on failure. Outputs and failed staging remain private local media.

Primary references: [FFmpeg timestamp and fps-mode controls](https://ffmpeg.org/ffmpeg.html)
explain passthrough/copyts and muxer qualifications; [MP4 muxer controls](https://ffmpeg.org/ffmpeg-formats.html)
cover faststart, movie/video timescales and edit lists; [loudnorm filter](https://ffmpeg.org/ffmpeg-filters.html#loudnorm)
documents loudness and true-peak measurement. None establishes perceptual codec
quality or proves a musician's performance accuracy.

Qualification: 42 owner/independent tests passed in 13.665 seconds with
`env PYTHONPATH=tests .venv/bin/python -m unittest test_share_export
 test_share_export_audit -v`. The worker was unchanged before/after at SHA256
`6894315f90cb8cbfb5ecd1cf219ac0d70f65a5da45fc0282fc1e63d2d5175d8c`;
the qualified owned runner is `790ac58f1924db2607087c6ab1cdae5d813ba24eda610af1f396d77e93d06584`.
The owner test file is `44cc03eb066cef251117e8b24adebbbbae2b3372d4d3a3e5d39409dff3b4d255`
and independent audit file is `184eb77bf792475c30a2be0b2556a933c7a7ed89a14f399ef94ebf0bf0d3985a`.
The retained exact log `artifacts/share-export-worker-final-fixtures.log` is
`0a4efdb778cfdb7db12f3895c3b9b57d1a58a627cc687a2c18be793c70e7ab33`.

Generated two-second 320×240 VFR fixtures exercise default H.264, explicit HEVC
and copy paths: 41 presentation packets retain exact source PTS and two-second
tail, native 44.1 kHz stereo remains, AAC measurement/padding checks pass and
copy additionally retains coded payload/DTS/durations. Deterministic randomized
geometry cases test even sizes, no upscaling and aspect bounds. Refusal fixtures
cover invalid controls/metadata, changed source, AAC retry limits, decode errors,
atomic races, committed/unknown publication recovery, signal timer restoration,
long diagnostic bounds and the fixed hook envelope. Two real inert process-tree
fixtures qualify owned inner-deadline and CLI-alarm cleanup; they do not establish
containment for deliberately escaped sessions or generic outer-wrapper kill.
No actual take was processed by this worker during qualification. Listening,
actual full-take runtime, typed-hook admission and master adoption remain separate.

An earlier broad discovery also included eight not-yet-admitted hook tests;
its 50-test result had one failure and twelve subtest errors because the live
catalog still exposed 29 tools. That negative log is retained at
`artifacts/share-export-final-fixtures.log`; it is not the 42-test worker seal.
Root owns integration/actual-take release within existing user authorization,
not a new approval prompt.

The fixed local hook adds `--tool-envelope`: known domain failures retain their
JSON evidence at exit zero solely for transport; the hook classifies status as
failure. Standalone CLI domain failures still exit two. Optional
`diagnostic_fields_omitted` explicitly marks transport projections; full details
remain in the hash-bound failure receipt. No omitted selector implies absence.
