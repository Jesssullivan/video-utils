# Capture-profile application: native A/V qualification plan

Actor `media_latency`; authority root's plan-only assignment under the active
parallel goal, R-HOOK-CONVERGENCE-20261004 and R-N13. Implementation owner
`rhythm_analysis`, independent refusal/release reviewer `release_review`, root
owns execution release, integration and publication. This document creates no
execution release. No actual recording, DSP, model, profile, source worker,
master, run or latest pointer has been changed by this lane.

Definition of done: one generated FOSS native A/V fixture proves the real
authoring-to-application-to-export path with current frozen workers, including
nonzero origins, capture preroll removal, measured filter-delay compensation,
native extent/channels, copied picture clocks and final delivery peak. Existing
mocked/refusal tests remain separate evidence. Success is an immutable
`rendered_unreviewed` candidate; listening, physical capture synchronization,
musical correctness and master adoption remain false or unverified.

## Release and environment

Before any execution, root records exact application/author/media source hashes,
positive independent frozen-source/refusal audit receipts, and release of this
single generated trial. Tool-25 author is currently pinned to
`7d2820878826c87aabf2ab60b73c997b9d406b7f3ff8943d6012ed967444c355`;
The owner and independent reviewer subsequently confirmed final application
SHA256 `31eafcc8a76a36981945a1f680b21ab986f5a7464c9f8060559ce4b127198621`
and media SHA256
`91443154251888c9e74670790766b289a2618f85f3be806d60ca26882faa9d94`;
this lane independently rehashed all three current source files. Their combined
36 metadata/inert-process tests passed in 6.231 seconds, as reported by the
owners; this is not a native render result. Both owners found no material
contract gap in this plan. Pin these identities in the execution release.
Do not execute a changing worker or upgrade the producer hashes to make stale
authoring pass. Typed tool-28 admission/publication is a separate state.

Use an explicit existing Python interpreter with stdlib, existing pinned FFmpeg
and FFprobe through `FFMPEG`/`FFPROBE`, and record executable paths, binary hashes,
versions and needed filter/codec support (`afftdn`, `asendcmd`, `concat`, `loudnorm`,
`select`, PCM, AAC and the installed picture encoder). Set mathematical threads
to two before imports; FFmpeg/filter threads remain two. No package/model
downloads, codec installs, GPU, daemon, host or plugin changes. Whole fixture
qualification budget is at most 600 seconds, with each operation using the
remaining budget; authoring remains at most 60 seconds. Root's bounded owned
process runner records leader/group ownership and stops only this trial's
verified live processes on timeout. Finite bounded JSON/logs, fresh paths and
retained failure receipts are required.
Qualified cleanup covers the created process session/group; descendants that
escape that session/group are outside its proven scope. Historical commands and
probe paths retain actual private staging execution locations, while current
published selectors and hashes identify the final candidate.

## One generated fixture

Create exactly one new private fixture beneath
`artifacts/experiments/capture-application-native-qualification/<trial>/`; keep
fixture generation specification, commands, seeds, hashes and native facts.
The original fixture is never overwritten. Auxiliary generated reference PCM
belongs to this same fixture, not an additional media case.

The proposed fixture has eight seconds of stereo PCM at 44,100 Hz: exactly
352,800 sample frames per channel. Use deterministic low-level generated noise,
near-32 Hz sustained guitar-like tone after 1.5 seconds, a distinct low harmonic
or tone/amplitude in the other channel, a few bounded click/pick-like attacks
after 3 seconds, and an ending low-tone tail reaching the excerpt boundary.
This is a declared synthetic signal, not a real guitar or isolated fan model.
Provide a music/click-free generated noise opportunity from audio-relative
0.25 to 1.00 seconds (0.75 seconds); use no hidden post-result selection.

Mux uncompressed native PCM audio so source AAC priming is absent. Generate
8.5 seconds of small picture at 24 fps, preserving PTS while omitting frames
with `n mod 7 == 3` to create known VFR gaps; 204 nominal frames minus 29 omitted
frames gives 175 decoded picture frames. Use a one-second common container
offset and an additional 0.5-second audio offset. Expected source picture starts
at 1 second, first decoded audio at 1.5 seconds, relative offset 0.5 seconds;
last picture extent is 9.5 seconds on this source clock. Confirm these expected
facts using actual bounded probe/decode results. A muxer edit-list discrepancy
must be investigated, not silently replaced by the expected constants.

## Author then apply

1. Obtain a new source-bound bypass baseline through existing `media.clean`,
   using only this generated fixture. Record original SHA, source PCM SHA/header,
   352,800 sample frames, stereo 44.1 kHz, first decoded audio origin 1.5 seconds,
   native source extent, no-time-stretch receipt and picture clock evidence.
   Use direct existing functions or a workflow with explicit `--no-latest`;
   never alter the actual-take latest pointer for fixture convenience.
2. Save a real tool-25 sixteen-field review sidecar inside this generated run,
   with current original/manifest/source-PCM hashes and exact audio-relative
   bounds `[11025,44100)` native samples. Record generator-based interval review
   and root's released experimental scope honestly; no operator listening or
   authenticated identity claim. Music/click uncertainty may remain unknown
   even though the generator has a declared noise-only opportunity. Set
   `experimental_capture_render` only from the actual released scope.
3. Invoke existing `capture_profile` with explicit controls: reduction 3 dB,
   noise floor −40 dB, adaptivity 0, gain smoothing 0, integrated −18 LUFS,
   true peak −1.5 dBTP; omit EQ/compressor. Require exactly
   `authored_unrendered`, a new runnable profile/receipt with returned byte SHA,
   unchanged parent/source/context, and no rendered/learned-noise claim.
4. After frozen release, invoke exactly
   `python scripts/apply_capture_profile.py INPUT --authoring-dir AUTHORING_DIR
   --receipt-sha256 RETURNED_SHA --timeout-seconds REMAINING_SECONDS`.
   No caller DSP controls or alternate source/receipt are added. Follow only
   explicitly returned current artifact selectors; no newest scan. Require one
   atomically published fresh candidate and its application receipt, manifest,
   copied applied profile and export outcome, each hash-bound and current.

## Hard numerical and provenance checks

- Every native `source`, `denoised`, `residue`, `baseline` and `cleaned` WAV has
  exactly 352,800 sample frames, 44,100 Hz, two channels and finite samples.
  No `processed.wav` exists when EQ/compressor were omitted. Profile/capture
  requested seconds and encoded seconds both map to `[11025,44100)`; source
  capture media span is `[1.75,2.50)` seconds. Frame/rate/channel/count changes
  are exact failures, not tolerance-qualified.
- Capture training is 33,075 samples; the 100 ms guard is 4,410 samples;
  removed private preroll is 37,485 samples. Independently calibrated afftdn
  delay must be measured on both channels with matching impulse offsets,
  recorded as `measured_and_compensated` and remaining bulk delay zero.
  The current 44.1 kHz implementation predicts 1,102 samples; report the measured
  result and reject a disagreement rather than forcing this expected value.
  The expected final filter trim is `[38587,391387)` before source-axis reset.
  All original-end samples retain declared padding/trim support.
- Recompute source-minus-pure-denoised residue on the full native array.
  With float32 source/denoised/residue and values bounded below full scale, use
  absolute sample error at most `2**-22`; inspect first/last support separately.
  This verifies arithmetic/extent only. It does not make denoise input-dependent
  components into isolated music/fan outputs. Do not compare residue against
  normalized or later-stage PCM.
- Independently inspect the real exported video: 175 decoded frames, all ordered
  picture packet payload hashes unchanged, rational PTS/DTS/durations preserved
  under the expected −1-second common translation, including VFR gaps and final
  extent. Use the frozen exporter's declared rational-clock tolerance, retaining
  its measured residuals; no average-rate reconstruction or tolerance widening.
- Delivery audio remains 44.1 kHz/stereo. Relative decoded audio/video origin
  remains 0.5 seconds within the existing exporter's stated AAC tolerance
  `1024/44100 + 0.002` seconds. Record packet priming/skip/discard/edit-list
  evidence and decoded extent where available; AAC raw decoded padding is not
  exact PCM-master extent or new DSP delay. Native master count remains exact.
- Require all exporter verification flags, final measured AAC true peak
  `<= −1.5 dBTP` without relaxed tolerance, bounded delivery gain-attempt receipts,
  and unchanged PCM-master hash across export. Record measured integrated
  loudness and the frozen worker's existing acceptance rule; do not invent a
  new loudness tolerance. Finite low-band/tail/attack measurements are diagnostic,
  not a gate asserting perceptual preservation or guaranteed guitar gain.
- Rehash fixture original, parent manifest/all parent artifacts, review,
  authoring receipt/profile/context, actual published source/master/preview
  receipts and the latest pointer before/after as appropriate. All originals,
  parent and current actual media/latest remain identical. The only allowed
  additions are this generated baseline, authored profile and separate candidate.

## Refusal/failure evidence and decision

Keep injected metadata/process failures distinct from numerical integration
acceptance. Reuse the frozen owner/reviewer tests for stale receipt/profile/source
or context, draft/reselection/missing render scope, malformed headers/origin,
symlinks/traversal, changed input, timeout/output bound, subprocess-inspection
failure, exporter missing proof/overshoot and publication collision. Do not add
another generated audio fixture or damage originals to demonstrate refusal.
Those tests must prove nonzero failure, no success candidate, owned-process
cleanup and bounded retained failure receipts; they cannot substitute for the
real positive FFmpeg render/export above.

Any exact extent/channel/origin/capture mismatch, unresolved calibration,
unexpected picture payload/clock change, missing exporter proof, final AAC
peak failure, stale input, pointer/master mutation or exceeded budget rejects
native qualification. Retain evidence and the generated failed trial; do not
adopt or silently repair metadata. On pass, root may admit the bounded route
while retaining `rendered_unreviewed`, `listening_accepted: false`,
`master_adopted: false`, `physical_audio_video_sync_verified: false` and no
best-tone/isolated-source/performance verdict.

Optional actual-take application is a subsequent root-owned release of one
existing approximately 151-second source (within the worker's 300-second cap),
with a newly verified exact source/parent/authored receipt and independent
candidate audit. It is not authorized by fixture success or this plan, and
never overwrites the accepted/published original, master, marked preview or
latest pointer. No actual-take application is performed by this lane.
