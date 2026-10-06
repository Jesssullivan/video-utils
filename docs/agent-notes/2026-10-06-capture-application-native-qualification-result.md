# Generated native capture application qualification

Root released one exact generated trial in
`2026-10-06-root-capture-application-native-release.json` (SHA256
`56e49d0789fa84e8a0d75f03d222f4bda291995a519810c63d8f297d94e98b3c`).
Actor `/root/media_latency` launched owned execution session 23980 once, under
R-N11/R-N13. It returned exit 0 after 45.707 seconds. No rerun or settings
adjustment occurred. The immutable plan, final application/author/media sources,
preregistration and existing media binary identities remained pinned.

The retained trial is
`artifacts/experiments/capture-application-native-qualification/native-20261006T0255/`;
its `receipt.json` has SHA256
`04a6806591c83e449c9a15242226c1d106d03c1b229a996cd0ba6aeb21a0c668`.
The fresh candidate is `artifacts/runs/20261006T025631Z-d29c3f02709c`.
The sibling dated result JSON records exact application, manifest, export,
source-picture, AAC timing and generated source selectors and hashes.

The generated reference's signed stereo samples mapped exactly by `/32768` to
the baseline float32 decode; the candidate source decode exactly matched it.
All native stages retained 352800 sample frames, 44100 Hz and two channels.
Capture bounds were `[11025,44100)` with 37485 preroll samples. The measured
1102-sample denoising delay was compensated with zero recorded remaining shift.
Maximum source-minus-denoised residue error was `4.656612873077393e-10`; first
and final boundary errors were zero and `5.820766091346741e-11` respectively.
Those checks establish sample transport and extent, not preservation of real
guitar notes or musical quality.

The original picture starts at 1 second and decoded source audio at 1.5 seconds.
All 175 decoded VFR picture frame timestamps and durations survived export with
the explicit −1-second translation, ending at 8.5 seconds in the exported clock.
Exporter packet payload and timeline checks passed. Independent first decoded
AAC timing measured `5248/11025` seconds relative to picture zero, approximately
24 ms earlier than the intended 0.5-second offset. This is within the frozen
`5561/220500`-second tolerance (1024 AAC samples plus 2 ms); it is not exact
sample alignment or physical synchronization. Raw AAC packet padding and decoded
frame extents remain separate from the native PCM sample count in
`delivery-audio-timing.json`.

Final decoded AAC measured −18.02 LUFS and −6.27 dBTP, passing the strict
−1.5 dBTP ceiling on the first encode with zero additional delivery attenuation.
All ten protected actual/latest identities and eleven generated parent/source
identities were checked unchanged. The original, current master, reports,
published video and latest pointer were preserved. Candidate status remains
`rendered_unreviewed`; no listening, musical quality, master adoption, AU/Logic
acceptance or native editor import is asserted.

Independent closure: release_review separately verified the saved arrays and
fresh native metadata, all 175 ordered packet payload hashes/timestamps/durations,
decoded frame clocks, AAC origin/padding and protected identities. Its durable
`2026-10-06-capture-application-native-artifact-audit.json` has SHA256
`a8e5b095e5659feaa3b5904e8e41fbde1452beaa52810a2401fac40f2d9d93fa`;
the detailed trial `independent-audit/receipt.json` has SHA256
`c34c29fb169f48e5d21d61a9582bc5a19d7ad8c20e5a851c06011ac1ae7916f9`.
This closure leaves the earlier result JSON's pre-readback status intact.

Status: generated native/export integration and independent artifact audit
passed. Root separately released one actual NR8/NR10 pair through its exact
`2026-10-06-root-actual-nr8-nr10-render-release.json`; those outputs remain
unreviewed candidates, with listening and master acceptance separate.
