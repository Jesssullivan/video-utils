# Fixed generated-bank learned-pitch numerical pilot

Root's exact numerical release `1d599a67bb3bd176c50607983818cfa39e43c37ebc69686e893c3d8194d34f23`
authorized the frozen four-job discovery and subsequent pure evaluator. Authority:
operator parallel goal, `AGENTS.md`, R-HOOK-CONVERGENCE-20261004/R-N11/R-N13.
This receipt records direct CLI proof, not MCP dispatch or real-guitar acceptance.

Discovery completed on the unchanged corrected technical-v2 bank: clean missing-F0
8 seconds, clean tuning ladder 8, legato mixture 6, sweep/polyphony mixture 8.
Opaque component aliases received no truth/score/case names. Fixed thresholds
0.5/0.3 and project 127.7/25-ms presets were not tuned. Thirty seconds yielded
19 model windows, 2,580 rows and 4,623,360 raw numeric bytes. The maximum measured
worker RSS was 167,477,248 bytes; worker elapsed time summed to 39.817 seconds.
Raw arrays preserve all three clocks and window/padding provenance.

Predictions were sealed at
`artifacts/benchmarks/learned-numerical-pilot-20261006T0131/predictions-frozen.json`,
SHA256 `3149bf5f6bc0b716b2d969ae5f99faf53c574ccf4f36bd46a7451e9044d7551e`, before
the learned index `e565bb13847bb7f29c64a571f17d200f12dc21853154a39400516e52657bcf5f`
introduced evaluation truth bindings. Source, registry, worker, runtime and
prediction hashes were rechecked; originals, pYIN, models and current demo stayed
unchanged.

The separate evaluator completed in 15.853 seconds with regression alerts and
passed structural/unsupported-claim gates. Its complete receipt is
`artifacts/benchmarks/learned-numerical-evaluation-20261006T0133/learned-pitch-calibration.json`,
SHA256 `655819f1dbe5150b0de6f6e8f05cdbd11d95c6dab9f062b65c77dcd45d8790c7`.
Frame/event error CSVs and `scalar-metrics.csv` retain plot-ready values,
numerators, denominators and null reasons. The dated machine receipt
`docs/agent-notes/2026-10-06-learned-pitch-numerical.json`, SHA256
`ed7395ca49bf615506c9b1790794ecc6ecbd927a1f41cbf4ef18311e21c87fe5`, binds artifacts,
resource receipts, environment, hashes, clocks, scope and operational failures.

## Coverage and negative evidence

Native full-input mono eligibility is only 426 rows, all in missing-F0. Other
rows are 1,018 input-padding, 1,006 transition-crossing and 130 polyphonic rows.
There are no native absence rows: false-alarm rate is **null, N=0**. Neither
transition exclusions nor padding establish successful abstention or accuracy.

Missing-F0 native fundamental accuracy is **34/426 (7.98%)**. Chroma matches
426/426 but octave errors are **392/426 (92.02%)**, with median signed pitch error
approximately +2,400 cents. No octave repair was applied. This is the corrected
eight-second linear harmonic bank case; the earlier separate three-second proxy's
0/258 pointwise C1 diagnostic remains a different observation.

The pointwise model-clock diagnostic has different support and is not whole-input
acceptance:

| Generated case | Pointwise fundamental matches / voiced-reference N | Pointwise absence false voices / N |
|---|---:|---:|
| Missing-F0 | 65 / 605 | 0 / 83 |
| Tuning ladder | 405 / 466 | 46 / 222 |
| Legato-transition proxy | 357 / 423 | 2 / 93 |
| Sweep/polyphony proxy, mono spans | 254 / 297 | 23 / 261 |

Pointwise aggregation is 1,081/1,791 fundamental matches and 71/659 absence false
voices. The polyphonic chord pointwise set comparison has 130 rows, 144 voice TP,
0 FP and 246 FN, out of 390 generated reference voices. It does not qualify
full-input chord accuracy or real tapping/sweep transcription. Both alternate
clocks and paired pYIN branches remain in the complete receipt with independent
support and exclusions; no estimator or clock was selected by truth.

## Project decoder tradeoffs

| Generated case | 127.7-ms onset TP / reference N; FP | 25-ms onset TP / reference N; FP | 127.7 / 25-ms onset+offset TP |
|---|---:|---:|---:|
| Missing-F0 | 0 / 1; 9 | 0 / 1; 12 | 0 / 0 |
| Tuning ladder | 7 / 9; 9 | 7 / 9; 12 | 0 / 0 |
| Legato-transition proxy | 5 / 5; 0 | 5 / 5; 4 | 5 / 5 |
| Sweep/polyphony proxy | 7 / 18; 6 | 15 / 18; 18 | 4 / 12 |

The two project decoders produce 43/73 event candidates. The shorter floor adds
sweep matches and false candidates; tuning-ladder offset matching remains zero.
Legato proxy agreement concerns a generated score and known signal transitions,
not physical technique or musician performance. Timing residuals retain their
signed values and offset censoring; no capture latency is calibrated. No accepted
default, complete transcription, real-note grade or listening acceptance follows.

## Retained operational failures

The first discovery attempt stopped before decoding/inference because `ffprobe`
was absent from PATH. Its owned PID 20395 had exited; the diagnostic remains under
`learned-numerical-pilot-20261006T0129`. A new invocation used the existing verified
FFmpeg/FFprobe 8.1.2 binaries in
`/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/`.
No binary download, settings change or label-based retry occurred.

The first evaluation invocation used relative index paths and retained
`failed_structural/path_outside_benchmark_root` without metrics under
`learned-numerical-evaluation-20261006T0132`. The frozen evaluator's descendant
lookup expects absolute parents; the successful invocation used absolute paths
against the exact same sealed predictions in a new output. This CLI path bug is
reported to root for a later source fix; evaluator SHA256 remains
`1fb883026b842857f72a70c8bf2fb757330b9ac705be36914f7a4c50cb8f7374` throughout.
Both operational failures are preserved and do not alter the numerical cohort.
