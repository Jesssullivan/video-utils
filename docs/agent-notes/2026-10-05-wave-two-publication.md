# Nineteen-tool publication and calibrated demo

Authority: operator implementation, parallel-work and ten-hour goal requests;
R-HOOK-CONVERGENCE-20261004, R-N11/R-N12/R-N13. Root owns integration.

The prompt archive and TEN_HOUR_PLAN preserve and reassert today's scope.
The active goal was created at 20:49:34 UTC October 5, with a planned end of
06:49:34 UTC October 6. This delivery does not complete the goal.

## Actual local demo

Run: `artifacts/runs/20261005T211103Z-c6d0bac2fcd2`. The Documents recording is
unchanged, SHA256 `a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.
Its 44.1 kHz mono decode has 6,657,385 samples. The master measures −18.01 LUFS
and −1.50 dBTP. Final decoded AAC measures −18.07 LUFS and −1.56 dBTP after
a bounded −0.06 dB feed adjustment. The initial −1.49 dBTP export is preserved
in `export-revisions/initial-unreviewed`. All 3,631 picture packet payloads and
timestamps match source. The calibrated 1,102-sample FFT denoiser delay is
compensated, preserving rate, channels, length and tail. Physical capture A/V
synchronization and listening acceptance remain unverified.

Automatic discovery produced 48 candidate regions, 14 recurrence pairs and
186 review/navigation flags. Sparse DTW adds 11 comparison hypotheses across
14 pairs. These are not confirmed mistakes. Detection-only analysis finds
219 click candidates, with metronome identity unverified and audio unchanged.
Pitch samples 20 seconds across the take, including its ending (13.25% coverage),
producing 420 voiced branch hypotheses and 2,084 abstentions, not unique notes.
Meter remains unknown; tonal tonic/mode remain null. No model weights downloaded.

## Verification and publication

The local locked analysis environment passed all 219 tests without skips in
160.966 seconds. Separate MCP checks passed 37 tests. All 19 typed tools, exact
skill prompt bodies and skill validations were independently verified. Fixtures
cover 32 Hz preservation, missing fundamentals, legato, ambiguity, strict JSON,
bounded workers, provenance changes, immutable results, AAC repair and annotations.

Signed source commit `6f7d1965b3c99a9b2ed261d58ea8949c0d6a1b26` is published
to private Jesssullivan/video-utils main. GitHub confirms private visibility and
a verified signature. Hosted CI 37378799943 succeeded at 21:54:10 UTC: 219
discovered Python tests, 198 passed and 21 optional-backend skips; seven Rust
tests passed; secret scan passed. The local environment exercised those optional
backends. Earlier repair CI 37373960394 failed before any job steps because a
hosted runner could not be acquired after repeated attempts.

Root native checks pass ABI, Swift lifecycle and direct render-runtime audits.
Isolated native automation passes release and ASan/UBSan behavior checks. Its
last 10,000-block scheduling sample has p95 0.917 microseconds, maximum 63.958
microseconds and zero nominal deadline overruns; 1,000 processing calls record
zero C++ new calls. Source hashes are in `.cache/au-automation/receipt.json`.
These checks do not establish a hard real-time guarantee, packaged AU, auval,
Logic load, audio-device operation or native editor import.

Linear project content is refreshed. Updated D0 comment
`6b0c27ce-950d-4f6a-a492-2cd6e821e567` and active-goal comment
`18776874-b339-416f-a144-69a746ffdc9e` record source, demo and hosted evidence.
The six-owner continuation is in GRAPH_INTEGRATION_LANE.md. The active goal
continues; originals and derivatives remain ignored.

## Process receipt

Root | pid 79901, parent 79889, owned live gitleaks invocation verified by ps |
directory scan included regenerable private artifacts; replace with staged scan |
R-N11/R-N12/R-N13 | running | SIGTERM sent only to inspected owned process.
The bounded staged scan found no leaks in approximately 612 KB of source.
