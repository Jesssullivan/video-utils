# Restoration DSP latency lane — 2026-10-05

Authority: operator-authorized ten-hour parallel project work, repository AGENTS.md,
R-HOOK-CONVERGENCE-20261004 and R-N13. Owner: `media_latency`; files:
`scripts/media.py`, `tests/test_media.py`, this specification. Root integrates.

Plan: measure the synthetic benchmark's approximately 25 ms attack displacement
against decoded PCM, separate `afftdn` latency from loudness normalization, inspect
primary FFmpeg documentation and source, then compensate bounded filter delay
without changing sample count or cutting the source tail. Add meaningful 44.1/48 kHz
attack and low-frequency regression fixtures. Record exact delay and compensation
in the manifest. Existing published media and original recordings remain untouched.

Container start times and preserved picture packets prove mux timeline behavior;
they do not prove waveform alignment. Older runs without DSP latency calibration
must not acquire that stronger claim. Root will render a new run after verification.

Pending: measured latency, implementation, regression evidence and limitations.

## Measured behavior and correction

The tested executable is FFmpeg 8.1.2. Native-rate isolated attacks were delayed
**1102 samples at 44,100 Hz (24.988662 ms)** and **1200 samples at 48,000 Hz
(25 ms)** by the original `afftdn` chain. Sample count and WAV timestamps stayed
unchanged. A separate dynamic `loudnorm` pass displaced the same attack peaks by
zero samples at both rates. These measurements are saved privately under
`artifacts/latency-investigation/measurement.json`.

[FFmpeg 8.1 afftdn source](https://ffmpeg.org/doxygen/8.1/af__afftdn_8c_source.html)
sets its hop to integer `sample_rate / 80`, its window to three hops, and inserts
new samples at the two-hop offset in its overlap-add window. Its output retains
input frame properties. The two-hop bulk sample delay therefore survives ordinary
WAV rendering even when stream starts and sample extent match.

Before each denoising render, the worker now measures two isolated impulses in
**every output channel**, using the actual selected binary, rate and filter knobs.
It requires the observed peak delays to match the source-derived two-hop delay;
an unexpected implementation or unobservable calibration fails the render.
Calibration scratch files are deleted after measurement. Source audio receives
exactly that many padding samples **before filtering**, then the leading delay is
trimmed and output is trimmed to the original decoded sample count. Sample PTS
restart at zero. Padding before filtering lets late source attacks emerge; shifting
an already truncated delayed WAV would permanently lose the source tail.

`manifest.dsp_latency` records measured offsets, integer compensation, method,
remaining bulk delay, and the fact that a recording-specific waveform audit has
not been performed by this calibration. A bypass has no denoiser delay. Export
receipts distinguish container start verification from physical A/V synchronization;
legacy manifests without calibration do not gain a compensation claim.

[FFmpeg loudnorm documentation](https://ffmpeg.org/ffmpeg-filters.html#loudnorm)
states that an infeasible linear request falls back to dynamic normalization and
that dynamic true-peak processing upsamples to 192 kHz.
[FFmpeg 8.1 loudnorm source](https://ffmpeg.org/doxygen/8.1/af__loudnorm_8c_source.html)
manages buffered output timestamps and flushes buffered audio. The worker leaves
that internal compensation intact. The separate normalizer regression establishes
zero attack displacement for tested dynamic-mode fixtures; it does not prove every
future FFmpeg binary, profile or real recording is aligned.

## Regression and independent waveform evidence

On October 5 the **eight media tests passed** with the selected FFmpeg/ffprobe
8.1.2. The new meaningful regression covers both native sample rates, non-hop-aligned
sample counts, interior isolated attacks on a 32 Hz sustain and a final attack only
100 samples before EOF. Source, denoised, loudness-matched baseline and cleaned
master retain exactly the original extent. Corrected attack peak locations match
source sample indices exactly; final attacks survive. The fixture explicitly tests
dynamic normalization. An uncorrected denoiser control yields the expected two-hop
delay and fails tail preservation. Existing low-32-Hz preservation, bypass, source
immutability, packet timing and video-offset tests remain passing.

Independent FFT cross-correlation of retained old benchmark PCM windows found
1200-sample source→denoised displacement in all three palm-muted and legato windows
and the first low32 window; denoised→master was zero in every window. Later low32
sustain windows prefer a periodic alias at -299/-300 samples: 32 Hz has a 1500-sample
period at 48 kHz. This demonstrates why unconstrained correlation of a bass sustain
cannot by itself identify physical delay. Isolated attacks provide unambiguous
calibration. Private evidence: `artifacts/latency-investigation/benchmark-crosscorrelation.json`.

## Acceptance boundary

Existing rendered demo and benchmark media were not overwritten. Their denoising
bulk delay is an identified defect despite earlier passing container/PCM extent
checks. Root will generate a new actual take and benchmark run, then independently
audit waveform alignment, low-end energy and export evidence. No current receipt
claims complete physical A/V synchronization, listening acceptance, or timing
correctness of the musician. Filter calibration does not remove codec pre-ringing,
onset detector bias, changing spectral phase, or artistic performance timing.

## Delivery AAC true-peak repair

The fresh compensated real-take render's decoded AAC measured -1.49 dBTP against
its strict -1.50 dBTP ceiling. That 0.01 dB overshoot is a failed delivery check;
it is not accepted by introducing tolerance. The unchanged PCM master remains the
mastering output. The exporter now measures each delivery encode and, when needed,
attenuates only the AAC feed by the observed excess plus 0.05 dB of safety margin.
It permits at most three total encodes and at most 1.0 dB attenuation. An unchanged
source-picture stream is still verified by ordered packet payloads and timestamps.

Every attempt records feed gain, decoded loudness/true peak, exact encode hash and
ceiling verdict. The final decode must pass the original ceiling. Exhaustion or
unavailable measurements produces an explicit error, preserves the PCM master and
writes an `export-failures/*.json` receipt instead of publishing a delivery video.
A cached video with a failed ceiling is rejected; retain that export directory as a
revision before creating a fresh delivery. Gain changes neither correct performance
nor remove a metronome, and they do not rewrite the master or original recording.

A reproducible 220 Hz native-rate PCM fixture at -1.50 dBTP encoded to AAC at
-1.40 dBTP with the selected FFmpeg 8.1.2: actual codec overshoot, independent of
mastering. The integration regression requires a measured retry to bring decoded
AAC within the ceiling while keeping master hash, source pictures and timestamps.
A stubborn measured-overshoot fault case checks three-attempt exhaustion and the
retained failure receipt. Exact future codec behavior may differ; bounded decoded
measurements determine the result rather than assuming a fixed headroom succeeds.

After the delivery fix, **all ten media tests passed** with FFmpeg/ffprobe 8.1.2
(19.388 seconds). The actual overshoot/retry fixture and bounded failure receipt
checks passed alongside the existing latency, low-end and export protections.

## WAV ingestion origin follow-up

The extended-workflow WAV fixture exposed absent FFprobe stream-start metadata.
Root now probes one decoded audio packet/frame for its timestamp when stream
metadata omits the start. The source probe retains null, while the run timeline
records the measured decoded origin and command. No blanket zero or container
start substitution occurs. This is the decoded audio axis, not a BWF reference
time, acoustic delay or physical A/V synchronization measurement.

All eleven media tests passed locally in 15.369 seconds, including a 32 Hz WAV
with null stream metadata whose decoded-frame origin is zero and whose actual
rhythm worker inherits that origin successfully. Source bytes remain unchanged.
