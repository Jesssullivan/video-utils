# Phrase order-null: fewer false candidates, no default adoption

Authority: [root numerical release](2026-10-06-root-phrase-order-numerical-release.json)
SHA `9b13104224cc9030099d89afd62b39b6c8fa9a0cb1b064c8228d7dc4f1b7807a`,
operator parallel goal, AGENTS.md and R-HOOK-CONVERGENCE-20261004/R-N11/R-N13.
One fixed run, no tuning/retry or canonical/default/master changes. Both419/523
are now consumed confirmation data and may not become untouched data after tuning.

## Frozen inputs and outputs

| Item | SHA256 |
| --- | --- |
| Runner | `5582a5cf2b415b07a434b59f407da8c6e63fa9101001267dbba03f0cabe9f066` |
| Closed settings | `232f7503f58e9ebcb2b59b220b97755b7001683eccd80893634d8f6b777079a3` |
| Bank index | `42ff7501ea734378c22010c4765b58e66ed766627bbaedf81babddd4e69c8fa8` |
| Construction readback | `6e7c73553af7489650d48e22af70a599b4424aa84a326f02a8db7696b83fca80` |
| Final `evaluation.json` | `cc3e28ce269439a9a74c3c07035668198537135624b67d8873dd67651d1a2654` |
| Final `run.json` | `cc3a66cd5bd12ec10a081b25248bf06bcd487a9036248578d0c881c481ea21c1` |
| Owner `result-disposition-audit.json` | `cbdd8d886b7845f85491e54add31fe477f3459e61ab502a26e00af705be0acb7` |

Outputs: `artifacts/experiments/phrase-window-ablation/order-null-predictions-20261006T0152/`.
Bank: `artifacts/experiments/phrase-window-ablation/order-null-bank-20261006T0145/`.
[Preregistration](2026-10-06-phrase-order-null-prereg.md) and
[generation](2026-10-06-phrase-order-null-generation.md) retain the staged admissions.
[The separate audit](2026-10-06-phrase-order-null-result-audit.py) rechecks saved
JSON/hash/count/disposition evidence without rerunning inference or claiming an
independent matching verdict.

Tool session29646 completed exit0 in244.068506seconds, including setup,
preflight, ten sequential8-second cases, scoring and sealing. Both pinned binaries
passed byte checks and actual8.1.2 `-version` preflight. Two numerical threads,
120seconds/case and600seconds overall held. No timeout, signal or retry occurred.
Opaque worker argv supplied no seed/cohort/generated BPM/score. All predictions
were saved/hash-bound before truth opened; pretruth/final checks reverified copied
and canonical source, evaluator, instrument, settings, analysis/cache/prediction
and original/opaque audio hashes. Owner timestamp/branch-order checks support
stage isolation, not adversarial filesystem attestation.

## Identical full references and negative cases

Four generated positive reference pairs and six negative cases remain in every
arm's denominator. No candidate-dependent reference set was selected.

| Scope | Arm | IoU .5 TP/FP/FN | Precision | Recall | F1 | Negative FP |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| All | Bcontrol | 1/51/3 | .019231 | .25 | .035714 | 31 |
| All | Border | 1/16/3 | .058824 | .25 | .095238 | 8 |
| Seed419 | Bcontrol | 1/30/1 | .032258 | .5 | .060606 | 18 |
| Seed419 | Border | 1/10/1 | .090909 | .5 | .153846 | 5 |
| Seed523 | Bcontrol | 0/21/2 | 0 | 0 | 0 | 13 |
| Seed523 | Border | 0/6/2 | 0 | 0 | 0 | 3 |

At IoU **.75 both arms have0TP/4FN**, with52FP for control and17FP for order;
all precision/recall/F1 are zero. Negative-cohort false candidates: low32 **13→4**,
missing-F0 **18→4**, click/noise-only **0→0**. The click controls provide no positive
evidence of improved click-confound discrimination because neither arm proposed
anything there. Both preregistered relative criteria technically pass, but seed523
preserves zero recall. Absolute phrase discovery and strict boundaries remain poor.

## Common-reference endpoints and cap dispositions

Only419 legato is matched by both at IoU.5: **one common reference pair/four
endpoints**, with identical mean absolute error **.522025154seconds**. Signed
offsets in both arms are `[-.982135780, -.047518927, -.996531380, -.061914527]`.
No lost/gained reference IDs; seed523 common N=0 and endpoint error null. Full
unmatched reference IDs and false negatives remain visible. No endpoint gain.

Both arms use53 identical A proposals. B contrast removes one missing-F0 proposal,
leaving52 control candidates. Order margin removes35 more:23 negative-case false
proposals and12 positive-case false proposals, leaving17. **No ranked-cap
exclusion occurs in either arm**, so the reduction here is due to the guard and
not a changed truncation budget. Both cap10; max control count per case is10.

| Case | A proposals | Control retained | Order retained | Added margin exclusions |
| --- | ---: | ---: | ---: | ---: |
| 419 low32 | 9 | 9 | 3 | 6 |
| 419 missing-F0 | 9 | 9 | 2 | 7 |
| 419 click/noise | 0 | 0 | 0 | 0 |
| 419 palm | 3 | 3 | 0 | 3 |
| 419 legato | 10 | 10 | 6 | 4 |
| 523 low32 | 4 | 4 | 1 | 3 |
| 523 missing-F0 | 10 | 9 | 2 | 7 |
| 523 click/noise | 0 | 0 | 0 | 0 |
| 523 palm | 2 | 2 | 0 | 2 |
| 523 legato | 6 | 6 | 3 | 3 |

Every proposal keeps competitor medians/counts, rotated cosines/null median/margin,
threshold/cap disposition and original index. Detector/boundary confidence remains
unknown. The order filter cannot generally distinguish musical motifs from ordered
nuisance textures and can reject legitimate repetitive guitar. No adoption,
confirmed musical mistake, listening acceptance, plugin/Logic acceptance or
actual-take transfer is established. Independent final result review is assigned
by root separately; only source admission was independent at receipt creation.
