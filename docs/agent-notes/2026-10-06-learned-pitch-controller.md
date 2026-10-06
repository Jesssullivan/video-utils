# Bounded learned-pitch controller preparation

Authority: operator-authorized parallel project goal; repository `AGENTS.md`;
R-HOOK-CONVERGENCE-20261004, R-N11 owned-process signalling and R-N13 durable
evidence. Root owns inference release, integration and publication.

Implemented new `scripts/learned_pitch_pilot.py`, SHA256
`df7ca74708fa8b9ca09f5db9b06426ed215c409630a4cc8ba13fa9c52650ce38`, and
`tests/test_learned_pitch_pilot.py`, SHA256
`fdc816025d4dc51948aa0ba7e445ea4e0e3b6f6cdb289f13e9940d343f99cb1a`.
All 14 controller tests passed in 1.011 seconds. Tests use constructed metadata,
silence WAVs, mocked discovery receipts and inert owned child processes; they
never import or execute a model and establish no numerical model quality.

## Operator interface

```sh
python3 scripts/learned_pitch_pilot.py \
  --preregistration docs/agent-notes/2026-10-06-learned-pitch-bank-preregistration.json \
  --output artifacts/benchmarks/NEW_DIRECTORY --summary
```

This default prepares only source-identical opaque inputs and generic manifests.
Optional execution additionally requires `--execute --release RELEASE_JSON`.
The release is a finite bounded repository-local JSON object containing
`inference_authorized: true`, the exact `preregistration_sha256`, and the current
`controller_sha256`. This is the concrete root release evidence, not a new
operator approval request. No execution was performed in this lane.

Each discovery call receives only an opaque directory and fixed start/budget/
activation threshold flags. The filename `denoised.wav` is a compatibility name:
its manifest explicitly records an unprocessed byte-identical component alias,
`denoising_performed: false`, unchanged gain, generator sample-zero origin, and
native PCM extent. Truth content, fixture names, expected notes and scores are
not passed to discovery. Four jobs remain 8+8+6+8 seconds, 19 model windows,
2,580 retained rows, with the two project duration presets sharing raw inference.

The controller does not install dependencies, download models, change existing
bank/source/pYIN bytes, or invoke evaluation. It requires the qualified worker,
runtime manifest, model declaration, instrument registry and evaluator identities.
Fixed limits are two numerical threads, a whole-controller 900-second deadline,
the worker's 600-second bound, 1 GiB reported peak RSS, 20 MiB aggregate raw
numeric arrays and 5,000 events per preset. A new worker starts only with at least
610 seconds remaining. Failed or interrupted jobs retain prior prediction
receipts and cannot produce the complete index. Owned process groups are checked
for live non-zombie members before signalling; tests cover both timeout and a
leader that exits while an inherited child remains live.

Before sealing, the controller rechecks its source and preregistration, registries,
runtime, original waveforms, opaque aliases/manifests, bank/pYIN indices and every
comparison/archive hash. `predictions-frozen.json` is written before
`learned-pilot-index.json`, which introduces truth-path bindings for the separate
pure evaluator. The evaluator independently validates archive contents, clocks,
window support and metric denominators; a controller completion is not numerical
acceptance.

## Actual preparation evidence

The default command succeeded against the fixed bank and pYIN snapshot at
`artifacts/benchmarks/learned-controller-final-preparation-20261006T0127/`.
Its `preparation.json` binds the final controller above, preregistration
`0314cb209d9a2113ecb63f5bef48df541337d247d7992f88fc13f677105e4599`, bank
`3a6d117a50b32ad4f9e1b60921ee1b8a1d4376cc821ebcb31f14f4b8d80fdc73`, and
pYIN index `5c183df75f67dfa4b6d4a7b3c13b7d79d9fcbfa0408ce90d58a80017948ed343`.
All four waveform hashes, PCM16 mono 48 kHz headers and exact native sample
extents were verified. Waveform bytes were read; audio was not decoded into
analysis samples; no subprocess, model inference, raw activation reads or truth
content reads occurred. Earlier preparation under
`learned-controller-preparation-20261006T0130` preserves a superseded controller
identity and must not be executed against the final source.

Read-only generator/truth review resolves the suspected fundamental-regrowth
issue for this corrected bank: the missing-fundamental case is a linear harmonic
sum, and its existing rendered PCM joint-fit receipt reports F0 amplitude
`2.1125001369190132e-08` against absolute tolerance `5e-05`. That numeric fit is
the existing bank's evidence, not a recomputation by this controller. Earlier
tanh-based comparator proxies are separate. Full-context stable monophonic
eligibility is preregistered as 426 rows; stable native absence has denominator
zero and must retain a null false-alarm rate. Transition/padded cohorts remain
separately excluded or descriptive. No real-take note grading, listening
acceptance, model-accuracy claim or 30-second inference receipt is established.

Frozen counterparts remain unchanged: Basic Pitch worker
`720a1f76103426d1cc7580d213d3516f31b184295a50d873bda545ccc5a2d40e`, learned
evaluator `1fb883026b842857f72a70c8bf2fb757330b9ac705be36914f7a4c50cb8f7374`, and
published pYIN evaluator
`a91ce8e9386cc7c63c5a5d53b8233f2c46a1f42fdd06ab1ae0eea3dc83405805`.
Catalog and existing workers/tests were not edited. Independent plan-review
closure and root's exact inference release remain separate next steps.
