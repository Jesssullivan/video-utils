# Independent saved-result review: fresh phrase localization

Date: 2026-10-06. Actor: `/root/plan_review`. Authority: root's explicit
read-only numerical-audit assignment, repository AGENTS.md and
R-HOOK-CONVERGENCE-20261004 / R-N13. No source, settings, predictions, truth,
media, tracker or default was changed. No generation, inference, DSP or audio
decoding was performed.

**Verdict: the frozen evaluation is numerically consistent, but the experiment
does not qualify a useful phrase localizer or default adoption.** All three arms
recover zero of four generated reference pairs at both overlap thresholds.
Reject default adoption; retain the failed experimental result and prioritize
reference-aware review, user assertions and the actual tone comparison.

## Scope and independent method

The new [stdlib-only audit script](2026-10-06-phrase-localization-numerical-independent.py)
read 28 bounded JSON files: the bank, run, prediction seal, evaluation, twelve
predictions and twelve truth documents. It verified their pinned hashes before
parsing and again at completion. It independently reconstructed interval IoU,
typed endpoint matching, TP/FP/FN, precision/recall/F1 and their null denominators,
all twelve case rows, nine aggregate scopes, common-reference endpoint sets,
lost/gained reference IDs, coverage-count copies and the two relative criteria.
It imported no production evaluator or worker. WAVs, NPZ caches and their bytes
were not read; source audio identities were compared as saved metadata only.

One reference pair at most exists in each generated case, allowing independent
exhaustive matching without a general matching-library dependency. A pair match
requires both corresponding intervals to satisfy the stated IoU threshold;
typed endpoints compare first/second start/end separately. All four positive
references remain in the denominator, including cases with no proposals.

The seal records truth unopened and all twelve prediction hashes. Saved file
mtime ordering agrees with prediction→seal→evaluation; this is corroboration of
the recorded sequence, not independent observation of the original processes.
Owner source-admission and execution receipts remain separate evidence.

## Recomputed results

The bank contains twelve eight-second cases, four positive reference pairs and
eight negative cases across seeds 617 and 719. For both IoU 0.50 and 0.75:

| Arm | TP | FP | FN | Reference pairs recovered |
| --- | ---: | ---: | ---: | ---: |
| Araw | 0 | 9 | 4 | 0/4 |
| Border | 0 | 7 | 4 | 0/4 |
| L1 | 0 | 4 | 4 | 0/4 |

At each typed endpoint tolerance, 20, 50 and 100 ms, all arms have **0 TP and
16 FN**. Endpoint FP are 36, 28 and 16 for Araw, Border and L1 respectively.
All positive-scope precision, recall and F1 are zero. Empty negative scopes
retain null recall rather than reporting a fabricated success.

| Negative scope | Border false pairs | L1 false pairs |
| --- | ---: | ---: |
| Seed 617 | 2 | 0 |
| Seed 719 | 3 | 2 |
| All negative cases | 5 | 2 |

The earlier verbal handoff's **5→3** was a remaining-count error: three candidates
were removed, leaving **two**. The owner confirmed the correction and changed
only its prose receipt; the frozen evaluation and numerical receipt already
contained correct counts. Total predictions fell 7→4. L1 removes three negative
false pairs, retains two negative false pairs and retains two false pairs in
seed-617 positive cases. Seed-719 positive cases have no upstream proposals;
localization does not recover these missing phrases.

At both overlap thresholds, common-reference pairs/endpoints are **N=0** for
every case and aggregate. Lost/gained IDs are empty and endpoint MAE is null.
There is no matched-reference evidence of boundary improvement. Both per-seed
relative criteria are true because negative candidates do not increase and
recall remains zero. Preserving zero recall cannot satisfy useful navigation,
phrase accuracy, technical-guitar performance grading or musician acceptance.
These synthetic seeds are now consumed evaluation data; no further adaptation
on them should be represented as held-out qualification.

## Exact receipts

| Input / result | SHA-256 |
| --- | --- |
| Bank `fresh-bank-617-719-20261006T0332/fixtures.json` | `9b62a3498f8ed5c508cca68c904f4d868c3861280c2f707f1972f098d4f39e67` |
| Run `fresh-run-schema-repair-617-719-20261006T0408/run.json` | `3187e03a542eb6458b307edbff414a71c26fc871a405c00a3d3f919dc0ddb13a` |
| Prediction seal `predictions-frozen.json` | `2e7a9792d4277c72a06405508f27eb82a74cdc259f6bb79b856b9d0fb153b575` |
| Frozen `evaluation.json` | `5fafd1d3db2a2f74db3c439f9b40eebce04935e364b58b01cd6c6f27842f3003` |
| New independent script | `d23bde61494a29863138096258d2f985eae30ad68b7e74dfb9790f1376f99601` |
| New independent output JSON | `f8d9b36d77c4708885893ad266acaa91854b1d0bc996cf12dd0eb05a6c110b1e` |

Bank and run paths above are within `artifacts/experiments/phrase-localization/`.
The independently produced ignored output is
`artifacts/experiments/phrase-localization/independent-numerical-audit-20261006T0450.json`;
it includes all 28 input hashes, recomputed aggregate rows and unchanged-input
checks. The new durable script completed with exit 0. No owned service was
started or signalled; no process-cleanup exception was needed.
