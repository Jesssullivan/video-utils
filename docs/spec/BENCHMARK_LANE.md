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
  environment. Neither operation installs dependencies, downloads models,
  invokes a compiler, or acquires private source media.
- Save source/component/output SHA-256, exact worker/tool/config revisions,
  commands and measured durations in `benchmark.json`. Check input immutability,
  decoded PCM extent, coherent low-frequency gain, quiet-region noise change,
  and gain-adjusted error to the known synthetic clean reference. Do not treat
  master loudness changes as noise reduction.
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
