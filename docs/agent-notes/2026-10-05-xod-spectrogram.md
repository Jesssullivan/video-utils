# xoxd-spectrogram research and bounded feature proof

Actor: `/root/xod_spectrogram`. Recorded 2026-10-05T23:30 UTC.
Authority: R-HOOK-CONVERGENCE-20261004, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`; R-N12 advisory diagnostics and R-N13
durable receipts. The operator explicitly requested the additional parallel
lane. No process escape hatch or signalling was used.

## Identity and scope

Authenticated `gh api --paginate user/repos` found the private canonical
`xoxd-ai/xoxd-spectrogram`; user-owned public-name searches had no match.
Repository API main commit and detached ignored research clone both resolved to
`8264a38651c785aa0dd9c02e3569b2d979747d80`.
Clone: `artifacts/research/xoxd-spectrogram`, clean after checkout.
No sibling repository, environment, dependency lock, tool registry, master,
marker, analysis source or latest pointer changed.

The repository has no explicit LICENSE or SPDX package license. NOTICE defers
to `xoxd_theme` and operator publication ratification. This lane ran accessible
research code; it did not vendor or admit the package. Licensing remains an
integration prerequisite, not a blocker for tonight's restoration/video lanes.

## Executed proof

Existing Bun 1.4.2 executed the exact imported `src/core/pcen.ts` on supplied
feature matrices. Existing Python/librosa 0.11.0/NumPy 2.5.3 reconstructed xoxd
STFT/mel and checked Ruby golden output. Six generated WAVs cover three
technical-v2 clean/mix pairs; the actual decoded-source excerpt was [0,12]
seconds. Two numeric threads; numerical proof completed in 6.02 seconds.
No npm installation, full-package build or browser component acceptance occurred.

| Check | Result |
|---|---|
| Ruby log-mel maximum absolute difference | 4.931166586175095e-12 dB |
| Ruby default PCEN maximum absolute difference | 8.36664071357518e-12 |
| Exact TS streamed/batch maximum difference | 0 |
| Seven full input hashes after execution | Unchanged |
| Clean/mix flux cosine, default PCEN vs log | Lower on all three selected cases, power and magnitude policies |
| Actual-opening onset counts | 36 baseline, 29 power PCEN, 31 magnitude PCEN; unlabelled |

Cosine similarity and onset count are exploratory diagnostics, not detection
accuracy. No synthetic score was promoted to musician truth or video markers.
PCEN is a feature transform, not measured audible fan reduction. Half-time
phrase-window mismatch remains a separate experimental factor.

## Hash-bound evidence

Original movie SHA, recorded by the main run's manifest:
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.
That manifest binds decoded source WAV SHA
`d68e49688293b1fb8c7c2566e2ecd6e31df9972af013dd23454e15864654bd2a`,
independently rehashed by this proof. Its 16-kHz float32 12-second excerpt SHA:
`456e49d795b08a01276da0fc10ad0b89e8a1da2e85f2042f14d2ecd99503aa90`.
Fixed technical-v2 bank index SHA:
`3a6d117a50b32ad4f9e1b60921ee1b8a1d4376cc821ebcb31f14f4b8d80fdc73`.

Committed evidence copies contain settings, all seven input paths/hashes,
candidate times, metrics and executable worker provenance, with no audio:

- [`receipt.json`](evidence/xod-spectrogram/receipt.json), SHA
  `7ca43acdd46601926e60a734438e69e103bdfdf33f6a9ebf96818e957d988941`.
- [`proof.py`](evidence/xod-spectrogram/proof.py), SHA
  `1b32b59221b51086ce90d50e58ea3b65709900bdf9b6564210a5a8b2ddbbd48d`.
- [`pcen-proof-driver.ts`](evidence/xod-spectrogram/pcen-proof-driver.ts), SHA
  `5595e59567abfd9c959584035ccdb18d8d487ade58ac081bb69159d7e6831a90`.

The TypeScript file is our small import/iteration driver, **not** a copied XOD
PCEN implementation. Its executed filename was `pcen.ts`; that historical name
and the unchanged hash remain in the numerical receipt. Original XOD source
stays in the ignored isolated clone, with the source hash listed below.
Worker copies preserve the exact executed bytes. The additional owned
[`reproduce.py`](evidence/xod-spectrogram/reproduce.py) launcher verifies the
original clone's exact revision, clean state, PCEN source hash and both worker
hashes before preparing a fresh ignored output directory. It requires the
recorded immutable benchmark/main-run inputs. The larger feature matrices remain
ignored under `artifacts/research/xod-proof`.

Identity-only validation (no feature rerun):

```sh
.venv/bin/python docs/agent-notes/evidence/xod-spectrogram/reproduce.py --check-only
```

Fresh reproduction with a new output receipt, preserving the original receipt:

```sh
.venv/bin/python docs/agent-notes/evidence/xod-spectrogram/reproduce.py \
  --output "$PWD/artifacts/research/xod-proof-replay-NEW"
```

The launcher is later reproduction glue, not the originally executed worker;
its SHA-256 is
`d6131fba8a2f7fbd5eddac0a45988b640e35903b895e1020966e4de921df0e45`,
separate from the preserved run-source hashes above. `--check-only` passed on
the inspected clone. No copied private XOD implementation enters Git through
these evidence files.

Selected inspected source hashes:

| Path in canonical clone | SHA-256 |
|---|---|
| src/core/config.ts | 6997db12fe62fba0f76d54d19d9a3b427a2477f12946f2f3d7bf08d90b3151e8 |
| src/core/pcen.ts | 2ac3c72a1a73f23fda0075ece831cbaeb30b2f205b9c9ef78a0515d6bb24ac3c |
| src/core/mel.ts | c0d4b743b3a2d64897c92b805df89013c02d0d85fc2cc92e61c96c5af0f33544 |
| src/core/stft.ts | 0612ddb20460d80d9affce76c1e81d3c6c0ddf6db3857a3b0b2f1efec6449e19 |
| NOTICE | f98b0c080f66926a6d492b4248eb1b2cadf54129fa9353f82142542ae01dbf4b |
| pnpm-lock.yaml | 571b71725213ca912d5ed94a2e195e7531ae488e1e14d78a6b82ffc66bef2453 |

## Handoff

Research: [`XOD_SPECTROGRAM.md`](../research/XOD_SPECTROGRAM.md).
Next-week 5–7-hour bounded frontend/window ablation:
[`XOD_SPECTROGRAM_LANE.md`](../spec/XOD_SPECTROGRAM_LANE.md).
Recommend the reference conventions, goldens and future PCEN visualization;
retain current log-mel and use existing librosa for an optional calibrated
frontend before adding UI/package dependencies. Root owns publication and
factual Linear updates. This lane's deliverables are ready and frozen.
