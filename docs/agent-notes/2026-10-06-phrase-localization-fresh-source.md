# Fresh phrase-localization generator/harness source contract

Actor `/root/guitar_features` owns only the new pilot script, its source tests,
fresh preregistration files and this dated receipt. Root admitted source/test
work under R-HOOK-CONVERGENCE-20261004/R-N13 and the frozen L1 plan. Original
recordings, historical banks/results, canonical feature/rhythm workers, L1
worker, pitch workers, current demo, dependencies and tool catalog were preserved.

Candidate frozen source:

* `scripts/phrase_localization_pilot.py` SHA256
  `8eae0110995619d128a022e8f0882a522b6213c5899cfd41216128b9847abd6c`.
* `tests/test_phrase_localization_pilot.py` SHA256
  `002f98221411e1c63af950fc89501abea50a5be690380720d7b19d092379ead1`.
* Final preregistration SHA256
  `8b0e7969f702d0685e2d7176c4ee96c19b1325b2e9b3d848685e093405c4c000`.
* Frozen L1 worker SHA256
  `a64ff3acc5f18931e9975e96d1c6e80a1d454272fbf9dd4925b8b835b8c509de`;
  current admitted plan SHA256
  `71ab8f5b6641c33ac0bdf4bae4f4ba521c7fb22938d6547e4bc18a8c2639332b`
  retains the exact historical230022 plan body.

The root-pinned original order helper supplies the same Araw search and Border
contrast/order selection; the prior evaluator supplies the same primary IoU
matching. The benchmark helper supplies the rendered missing-F0 fit. Every
dependency's exact hash is committed in metadata/PINS, checked before importing
helpers and rechecked before sealing. The pinned canonical feature worker is
copied, then an exact one-line cache hook is added only to the isolated copy.
Canonical bytes are not changed. Child jobs receive opaque source aliases,
source hashes and mechanical layout/release hashes, without cohort, note,
motif, reference, generator BPM or truth paths.

## Public interfaces

`metadata()` is pure metadata. `construct_components(seed,cohort,rate=512)`
returns `array('d')` clean/fan/noise/click/mix values and generator truth; tiny
256/512Hz calls explicitly identify algebra-fixture scope. Native48k generation
is a later released phase. `score_case(references,arms,duration=8)` accepts
exact Araw/Border/L1 arm names and emits IoU and typed-boundary Ns/nulls plus
Border/L1 common endpoint comparisons. `aggregate_cases(rows)` micro-sums all,
seed and cohort counts. `score_sealed(...)` requires a complete hash-bound12-case
ledger and checks every prediction/artifact before truth opens. `roi_geometry`
is evaluation-only and cannot feed discovery. `treatment_estimates` checks raw
IDs/endpoints and credits only L1 physical cell support.

Numerical commands, **not executed in this source stage**:

```sh
python3 scripts/phrase_localization_pilot.py --generate \
  --plan docs/agent-notes/2026-10-06-phrase-localization-fresh-preregistration.json \
  --plan-sha256 8b0e7969f702d0685e2d7176c4ee96c19b1325b2e9b3d848685e093405c4c000 \
  --release docs/agent-notes/2026-10-06-root-phrase-localization-GENERATION.json \
  --release-sha256 ROOT_RELEASE_HASH --output artifacts/experiments/phrase-localization/NEW_BANK

python3 scripts/phrase_localization_pilot.py --run \
  --plan docs/agent-notes/2026-10-06-phrase-localization-fresh-preregistration.json \
  --plan-sha256 8b0e7969f702d0685e2d7176c4ee96c19b1325b2e9b3d848685e093405c4c000 \
  --release docs/agent-notes/2026-10-06-root-phrase-localization-RUN.json \
  --release-sha256 ROOT_RELEASE_HASH --bank-index NEW_BANK/fixtures.json \
  --bank-sha256 EXACT_RELEASED_BANK_HASH --output artifacts/experiments/phrase-localization/NEW_RUN
```

These placeholder release files do not exist and confer no admission. A real
root release must have actor`root`, scope`phrase-localization-fresh-617-719-v1`,
authorized phase`generate` or`run`, final plan/source hashes, exact dependency
map and budgets, and source-audit path/hash. Run release must additionally have
the exact completed `bank_sha256`. Both inputs/releases are regular files
beneath the assigned roots; output is a new non-symlink directory beneath
`artifacts/experiments/phrase-localization`.

The internal `--child-task PATH --child-task-sha256 HASH` is not an independent
unreleased inference entrypoint. Before importing NumPy or decoding it checks
the parent's sealed opaque admission, exact root run release, source membership,
plan/audit/source and copied-worker hashes, and qualified media hashes. Child
does not parse corpus truth, cohort geometry or note labels. A48k mono8second
input is decoded once to12800016k samples. Cache clocks retain501 centered
16ms frames and the full256ms FFT uncertainty; origin0 is a generated fact.

## Outputs, resource and failure evidence

Generation retains component WAVs, source/truth receipts, rendered proof,
`fixtures.json` and `generation.json`. Run retains byte-identical opaque aliases,
copied source bytes, mechanical `run-admission.json`, per-job task/analysis/
cache/proposal/clock/localization/prediction artifacts, `predictions-frozen.json`,
`evaluation.json`, and durable `run.json`. No source overwrite, downloads,
denoising, resampling of the native bank, gain processing, model inference or
default activation is part of this experiment.16k resampling is explicitly
analysis-only, separate from preserved48k inputs.

Thread environment is fixed at2. Cases run sequentially with112seconds maximum
child wait, reserving time inside120seconds/case and600seconds overall for
owned group cleanup and sealing. Other fixed caps are512 feature frames,
≤256×256 tiles,2million L1 cells/case,60 proposals/10 retained pairs,
1MiB cache expansion and1MB/audio file. Existing qualified FFmpeg/FFprobe8.1.2
paths/hashes are fixed in metadata; they are checked before and after execution.

Owned child processes use `start_new_session=True`. Cleanup inspects the exact
just-created PGID and records live members, ownership, reason, R-N11, signals
and result. A leader that already exited does not hide a live descendant.
Dead zombies do not count as live members. No other session is signalled.
Preparation, child failure, deadline, drift or evaluation errors retain a
partial/failure receipt. Incomplete discovery never opens truth. Missing pulse
is distinct from operational failure; empty musical predictions count full
reference misses. Partial L1 cell-budget abstentions remain visible and retain
full reference denominators. Cap/contrast/order/localization/no-proposal causes
are separately reported. Raw fallback does not count as localized support.

## Source verification and remaining stages

Owner20 standard-library source tests and the current25 independent constructed
tests passed together under `python3 -S`:

```sh
python3 -S -m unittest discover -s tests -p 'test_phrase_localization_*py' -q
# Ran45 tests in10.688s; OK
```

Tests cover exact prereg metadata/native non-grid geometry, shared nuisance,
continuous-phase repeated proxies/rests, tiny linear missing-F0 synthesis,
in-memory2LSB quantization and32Hz coefficient/octave rejection, prior minimum-
axis matching and best eligible mean reward, independent typed endpoint Ns,
negative nulls, full-denominator abstention, common-intersection nulls,
caps/claim/time/path guards, all12 predictions before truth, late stale artifact,
partial/truncated seals and exact-bank release. The owner also tested an owned
inert sleeping grandchild surviving its leader, then verified PGID cleanup.
No native WAV, fresh96second bank, real feature cache, FFmpeg decode, librosa
discovery or learned inference was run by these tests. Mocked orchestration uses
placeholder bytes and JSON, without valid WAV payloads or analysis.

This receipt is source evidence. Independent final audit and exact root numerical
release are still required before generating the bank. Any future measurement
must publish failures, strict-boundary/recall Ns and negative cohorts without
tuning the confirmation data. Useful absolute navigation accuracy, musician
listening, actual clip behavior and product adoption remain unverified.
