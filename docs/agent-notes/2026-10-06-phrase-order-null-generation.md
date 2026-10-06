# Phrase order-null bank: generation-only receipt

Authority: [root generation release](2026-10-06-root-phrase-order-generation-release.json)
SHA `f82b28c4bed63a807786fd2aeba1ea68fec38c591bc1340f940a6dbd5e4c23b4`,
operator parallel project authorization, AGENTS.md and
R-HOOK-CONVERGENCE-20261004 / R-N13. Root admitted generation only after the
[independent source review](2026-10-06-phrase-order-null-independent-review.md).
No discovery, model inference or phrase-quality evaluation has run.

Frozen input/source proofs are in the
[preregistration](2026-10-06-phrase-order-null-prereg.md): runner5582a5cf,
settings232f7503, metadata plan15c04b2f and independent review1a8c087c. Generation
started approximately01:45UTC October6 with tool session30195 and completed
exit0 with no deadline error. It used the held `--generate` command with the
0149 metadata plan, two numerical threads and generator120-second deadline.
No process signalling was needed.

| Saved item | SHA256 |
| --- | --- |
| `artifacts/experiments/phrase-window-ablation/order-null-bank-20261006T0145/fixtures.json` | `42ff7501ea734378c22010c4765b58e66ed766627bbaedf81babddd4e69c8fa8` |
| Same directory, `construction-readback.json` | `6e7c73553af7489650d48e22af70a599b4424aa84a326f02a8db7696b83fca80` |

The saved bank has ten8-second clips,80 native seconds, forty component WAVs
and ten source-bound truth JSONs. Six generated negatives (sustain, missing-F0,
click/noise-only across419/523) and four generated positive recurrence cases
(palm/legato across both seeds) match the frozen cohort set. Each WAV is48kHz
mono PCM16 with384000 frames. The owner reopened all native headers and sample
bytes, rehashed all51 artifacts including the bank index, and checked48 native
event axes. This is saved-byte construction evidence, not an independent review
or a musical inference result.

All five cohorts per seed have identical saved click/noise component hashes.
Click/noise-only clean PCM is exactly zero. The maximum saved mixture minus
clean/click/noise integer sum error is **oneLSB**, inside the preregistered
twoLSB rounding bound. No peak normalization was applied.

| Seed | Low32 clean joint fundamental amplitude | Missing-F0 clean joint fundamental amplitude |
| --- | ---: | ---: |
| 419 | .1744824823 | 4.2039180e-8 |
| 523 | .1644586185 | 4.2039180e-8 |

The reopened clean PCM fit uses DC plus sine/cosine harmonics1–7 over2–6seconds
at the declared C1 fundamental32.7031956626Hz. Both missing-F0 amplitudes are
below5e-5 and exactly reproduce the generator's saved construction checks.
The missing-F0 clean recipes are identical per seed because the harmonic
coefficients are fixed; nuisance parameters differ between seeds. These values
qualify the generated clean components only, not mixtures, pitch accuracy or a
real recording. Native PCM was interpreted for these construction checks; no
FFmpeg/audio-analysis primitive ran.

Before/after source hashes in `construction-readback.json` bind runner, settings,
0149 plan, source review, instrument context, rhythm/frontend/evaluator, original
guarded harness and root release. Every pin matched. The consumed211/307 bank,
canonical processing, current recording, masters, defaults and public registry
were untouched. Actual media executable/version preflight belongs to the later
discovery stage; root already independently checked executable byte hashes.

Exact-index discovery remains held. Root can inspect these construction proofs
and release only this bank SHA for the frozen equal-cap order-null comparison.
Save all predictions before opening generated truth for scoring; poor or zero
quality must remain visible and does not authorize default adoption.
