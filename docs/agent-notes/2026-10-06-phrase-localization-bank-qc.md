# Fresh localization bank: independent construction QC

Actor: `phrase_dag`. Authority: the root BANKQC assignment, the exact generation-only release below, R-HOOK-CONVERGENCE-20261004, and R-N13. This readback validates generated construction; discovery, inference, phrase accuracy scoring and adoption remain separate states.

The standard-library auditor completed successfully in 25.403 seconds on October 6, 2026. It checked all 60 saved WAV headers and PCM/file hashes, the 12 construction-truth JSON files and the source/context receipts: 89 bound files were unchanged on final readback. Each WAV is 48 kHz, mono PCM16, 384,000 samples (eight seconds). The bank contains 12 cases, 96 seconds, four positive recurrence cases and eight negative cases.

Fan and noise component files are identical across all six cohorts within each seed. Click files are identical across the five applicable cohorts; fan-envelope-only has a zero click component. Each rendered mix agrees with the sum of its four rendered components within two PCM16 LSB. Each positive case's two clean motif copies are byte-equivalent at the declared native sample placements. Construction metadata matches the preregistration; these positions were not used to alter discovery settings.

An independent joint DC/sine/cosine fit over the saved clean steady interval, using native sample coordinates at stride 24, measured a 32 Hz amplitude of **0.16999962015122208** for both seeds (target 0.17, tolerance 0.00005). The joint missing-fundamental fit included C1 and harmonics 2, 3, 4, 5 and 7; its C1 coefficient amplitude was **1.118936550544833e-7** for both seeds, below the 0.00005 bound. Every intended harmonic amplitude was within that bound. This fit differs slightly from the owner's fit because it also fits DC; neither number is a pitch-discovery result.

Exact selectors and digests:

| Artifact | SHA-256 |
| --- | --- |
| `artifacts/experiments/phrase-localization/fresh-bank-617-719-20261006T0332/fixtures.json` | `9b62a3498f8ed5c508cca68c904f4d868c3861280c2f707f1972f098d4f39e67` |
| Bank `generation.json` | `98b373e301b91e5d3ed29c34a03b9282b5749375e57904293067b041fc2c8230` |
| `scripts/phrase_localization_pilot.py`, before and after | `8eae0110995619d128a022e8f0882a522b6213c5899cfd41216128b9847abd6c` |
| `docs/agent-notes/2026-10-06-phrase-localization-fresh-preregistration.json` | `8b0e7969f702d0685e2d7176c4ee96c19b1325b2e9b3d848685e093405c4c000` |
| `docs/agent-notes/2026-10-06-root-phrase-localization-GENERATION.json` | `179b9af8fc6a342057fc790e99f055522be6bdbc5ed7ccdea5fe934829e942a3` |
| [Auditor](2026-10-06-phrase-localization-bank-qc.py) | `e0c7f2418f9eee60157730ee9a6fd7a7091f37d676369d875755d6241b68aca0` |
| [Full QC receipt](2026-10-06-phrase-localization-bank-qc.json) | `339c887f084d9682e4461ae5ef1365f43b0f38af84ed6c684832f6c0e3c534b8` |

The full receipt records every file binding, per-case component peaks and fits, and unchanged source/context pins. No waveform was regenerated; no frontend, model, cache, phrase discovery or accuracy evaluator ran. Native PCM was read and unpacked solely for construction measurements. No process was signalled. No current recording, canonical default, previous bank or published marker changed. The exact-bank numerical RUN release is still a root decision.
