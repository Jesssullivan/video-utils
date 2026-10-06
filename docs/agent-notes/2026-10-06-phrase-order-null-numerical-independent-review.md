# Independent phrase order-null numerical review

Authority: root assigned saved-JSON arithmetic review under the operator's
parallel-project authorization and R-HOOK-CONVERGENCE-20261004 / R-N13.
No generation, inference, waveform/cache reads, threshold edits or source
activation occurred. The earlier source-admission review remains frozen.

Verdict: the saved numerical results and filter attribution reproduce exactly.
The preregistered **relative** research criterion passes on both seeds, but
absolute recurrence accuracy remains poor. Do not adopt Border as a default
or promote these generated-signal results into real phrase correctness.

## Evidence and independent method

Prediction base: `artifacts/experiments/phrase-window-ablation/order-null-predictions-20261006T0152/`.
The ten-case, 80-second bank index remains
`42ff7501ea734378c22010c4765b58e66ed766627bbaedf81babddd4e69c8fa8`.
Run receipt `cc3a66cd5bd12ec10a081b25248bf06bcd487a9036248578d0c881c481ea21c1`;
evaluation `cc3e28ce269439a9a74c3c07035668198537135624b67d8873dd67651d1a2654`;
owner disposition receipt `cbdd8d886b7845f85491e54add31fe477f3459e61ab502a26e00af705be0acb7`.
The run records 244.068506 seconds, completed children and no signal receipts;
this audit did not execute those workers.

The separate [independent arithmetic script](2026-10-06-phrase-order-null-independent-numerical.py)
SHA256 `a7ea6759a5a0721fda56a91027f599f6d0fc7634bb2010eb9ba99f6dd786ca41`
imports only Python's standard library. It reads 24 bounded JSON files: bank,
run, evaluation, owner dispositions, ten predictions and ten truth receipts.
Every opened input hash matches its receipt and remains unchanged afterward.
It independently enumerates candidates against each case's zero/one reference,
requiring **both** span IoUs to meet .5/.75 and choosing the greatest mean IoU.
It reproduces every match index/score, TP/FP/FN, precision/recall/F1, unmatched
reference, aggregate, gate and common-reference offset within 1e-12.

It also recomputes qualification from saved contrast/null evidence, verifies
rotation offsets, median/margin arithmetic, identical ranking and cap handling,
and checks retained original proposal indices and all exclusion counts. This
validates saved arithmetic/attribution; it does not recompute feature cosines
from NPZ or prove the frontend's accuracy. All prediction mtimes precede the
evaluation mtime, corroborating the previously audited source ordering without
adversarial attestation.

Ignored independent output:
`artifacts/experiments/phrase-window-ablation/order-null-independent-numerical-20261006T0200.json`
SHA256 `e24d9499c8aa4f486fd19e7f36a4a0ce0d6b694d1f0ebaf49e9c43b9aaedb932`.
The durable script and this note preserve the independent method/conclusions.

## Recomputed result and boundaries

| Pair IoU | Arm | TP | FP | FN | Precision | Recall |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| .5 | Bcontrol | 1 | 51 | 3 | 1.923% | 25% |
| .5 | Border | 1 | 16 | 3 | 5.882% | 25% |
| .75 | Bcontrol | 0 | 52 | 4 | 0% | 0% |
| .75 | Border | 0 | 17 | 4 | 0% | 0% |

Negative candidate counts by seed/cohort are:

| Seed | Low32 sustain | Missing-F0 sustain | Click/noise-only | Total |
| --- | --- | --- | --- | --- |
| 419 | 9→3 | 9→2 | 0→0 | 18→5 |
| 523 | 4→1 | 9→2 | 0→0 | 13→3 |

Seed 419 loose-IoU recall remains 1/2; seed 523 remains **0/2**. Thus the
"recall not lower" gate on seed 523 preserves failure, not demonstrated recall.
Neither palm recurrence is recovered by either arm; Border retains no palm
candidate. The only matched reference is seed 419 legato. All four stricter-
IoU references are missed.

There are 53 initial proposals, one contrast exclusion, 52 Bcontrol survivors
and 17 Border survivors. No ranking cap fires. The 35 order-margin exclusions
remove 23 negative-cohort false candidates and 12 false candidates in positive
cases; they remove no loose-IoU true match. Both click/noise-only cases already
had zero Bcontrol candidates, so this experiment does not demonstrate an
additional click-only rejection gain.

Common-reference endpoint comparison includes exactly one pair/four offsets:
seed 419 legato, `generated-repeat-1`. Both arms have identical signed offsets
`[-0.9821357801, -0.0475189269, -0.9965313803, -0.0619145271]` seconds and MAE
0.5220251536 seconds. There are no lost or gained matched references. The
other nine cases have N=0, empty offsets and null MAE. These are primary-.5
matches; .75 has none. **No endpoint improvement is established.**

Continue this as an experimental false-candidate filter with explicit
abstention and review. Better proposal localization and recovery of palm/legato
phrases remain higher priorities than default activation. Seeds 419/523 are
now consumed evaluation evidence; future numerical tuning needs separately
held data. No confirmed musical mistake or musician/listening acceptance follows.
