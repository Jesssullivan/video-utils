# Reproducible technical-guitar benchmark lane

This lane measures synthetic fixture behavior and verifies existing artifact
lineage. It does not establish phone-recording quality, musical correctness,
listening acceptance, or separation of a real mono mixture.

## First implementation

- `scripts/benchmark.py fixtures --output NEW_DIRECTORY` creates deterministic
  48 kHz mono PCM16 clean, click, noise, and mixed references. Definitions and
  declared limits live in `program/benchmarks.json`; generated audio stays under
  ignored `artifacts/benchmarks/`. Fixtures include a sustained 32 Hz fundamental,
  distorted palm-muted repeated motifs, legato transitions, seeded noise, and
  coincident click/guitar attacks. Labels describe generated signals, not humans.
- `scripts/benchmark.py run --output NEW_DIRECTORY --profile conservative3`
  runs bounded serial restoration, rhythm, and phrase workers on these fixtures.
  Optional `--phrase-backend librosa` requires an already installed analysis
  environment and also benchmarks the dedicated click detector against the
  unprocessed generated mixture using its known click-only interval. That stage
  analyzes candidates and does not attenuate audio. Neither operation installs dependencies, downloads models,
  invokes a compiler, or acquires private source media.
- Save source/component/output SHA-256, exact worker/tool/config revisions,
  commands and measured durations in `benchmark.json`. Check input immutability,
  decoded PCM extent, coherent low-frequency gain, quiet-region noise change,
  and gain-adjusted error to the known synthetic clean reference. Do not treat
  master loudness changes as noise reduction.
- Generated WAV fixtures have a sample-zero origin from their generator, although
  the WAV container exposes no stream PTS. Keep the original media manifest;
  supply a separately hashed benchmark analysis manifest stating this synthetic
  origin explicitly. Never infer this assertion for the operator's media.
- Score detected click-time candidates against generated truth by one-to-one
  matching; retain the tolerance and signed offsets without automatic latency
  subtraction. Score phrase recurrence intervals against generated repeated
  regions, while retaining unknown semantic interpretation. Missing or changing
  worker schemas produce explicit unavailable/rejected metrics.

## Interfaces and limits

The first suite is `technical-v1`; configuration is versioned. Output directories
must be new and beneath this repository's `artifacts/benchmarks/`. Defaults:
48 kHz, at most three eight-second cases, serial execution, 120 seconds per
worker and 600 seconds overall. Workers inherit FFmpeg/ffprobe executable
overrides and must return JSON. Bound stdout/stderr and decoded media; an owned
worker process group is stopped on timeout under R-N11, with a receipt recorded
in the benchmark result. Source paths are local artifacts, never CI uploads.

`benchmark.json` distinguishes structural invariant failures from experimental
quality alerts. Timing precision/recall and phrase overlap are measurements;
absence of a known result schema is not a successful benchmark. A fixed
32 Hz attenuation alert is a conservative synthetic regression sentinel,
not a psychoacoustic acceptance threshold.

## Validation and integration

Tests must reject damaged source hashes and PCM extents, detect a deliberately
damaging high-pass response, distinguish gain-only changes from noise removal,
prevent duplicate event matches, and verify the fixture's intended signal
components and repeat labels. A bounded actual-worker smoke will retain its
receipt after implementation. Existing CI has a locked Nix environment and
stdlib tests; adding benchmark execution is root-owned and deferred until the
runner and actual locked tools pass locally. No CI acquisition or upload of
the operator's recording is authorized by this benchmark lane.

Click and pitch workers are being developed separately. Their exact schemas
will be adapted explicitly after publication; a generic spectral peak cannot
serve as a verified note or metronome identity. Root owns Just recipes, demo
orchestration, registry integration, and publication.

Authority: operator-requested ten-hour goal; R-HOOK-CONVERGENCE-20261004,
TIN-3692 comment `98cf680c-7299-4949-bfb2-60079053ad43`; R-N12 advisory findings,
R-N13 durable evidence.

## Observed initial baseline, October 5

Seven independent tests pass, including an owned-worker deadline/cancellation
receipt. The FFmpeg/ffprobe 8.1.2 and Python 3.12.14 stdlib suite completed all
three cases in 19.48 seconds. Local receipt:
`artifacts/benchmarks/technical-v1-source-comparison/benchmark.json`, SHA-256
`016fa219d9c2e1848849c55a074df95b8a2a828076820d08612140b76ac476f5`.

| Measurement | Observation | Interpretation |
| --- | --- | --- |
| 32 Hz sustained coherent amplitude | +0.000031 dB after denoising | This synthetic fundamental is retained |
| Noise-only RMS | -3.44 to -3.47 dB | Measured quiet-region reduction, before master gain |
| Source click-time candidates | Recall 1.0 within 20 ms | Generated mixture timing is detected by this fixture method |
| Denoised click-time candidates | Recall 0.0 within 20 ms | Candidates shift outside the fixed tolerance |
| Source-to-denoised candidate time | +25 ms median in all three cases | Processing delay and changed detector response remain confounded |
| Stdlib recurrence | No candidates for both known repeat fixtures | Eight-second motifs exceed this backend's useful recurrence coverage |

No timing correction was applied. Least-squares gain and raw waveform error
are phase-sensitive; they must not be advertised as denoising quality with an
uncalibrated sample delay. Preserve these findings for future latency accounting,
dedicated click evaluation, and optional multifeature phrase comparison.

After the separately owned media latency fix, a fresh stdlib suite completed
three cases in 61.13 seconds with consistent worker revisions. Receipt:
`artifacts/benchmarks/technical-v1-compensated-stdlib/benchmark.json`, SHA-256
`cca4799b9acfff246a034acf56901331ed1b06f7b4f7e76d7538b1188d0a7e44`.
The unchanged 20 ms click-time tolerance now yields recall 1.0 before and after
processing in every case; the measured source-to-denoised candidate shift is
0 ms. Quiet-region RMS reduction is 2.996 dB, and the sustained 32 Hz coherent
amplitude changes by +0.000003 dB. These synthetic observations support the
latency fix and preserve the prior failure receipt; real audiovisual/listening
acceptance remains separate.

The fresh optional suite used the existing Python 3.14.6 analysis environment
and completed three cases in 27.91 seconds with consistent worker revisions.
Receipt: `artifacts/benchmarks/technical-v1-compensated-optional/benchmark.json`,
SHA-256 `c9e9a99a9c88796b381dd03edccfe3418f5c752a25aa2ac49db14f4950cd87fb`.
Dedicated template candidates match all 23 generated click times per case
(precision/recall 1.0); no attenuation is enabled. Optional multifeature phrase
recurrence yields best paired interval IoU 0.935 for palm-muted and legato
fixtures. The sustained-tone case also yields texture recurrence candidates;
that establishes no musical-phrase interpretation. No packages were installed
by either benchmark invocation. These few timings are observations, not p95,
capacity, platform equivalence, or real-recording accuracy claims.
