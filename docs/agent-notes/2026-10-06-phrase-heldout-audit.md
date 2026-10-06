# Independent held-out phrase result audit

Verdict: **saved result arithmetic and matching verified; no default adoption**.
Actor `/root/plan_review`; root-assigned independent read-only audit under the
operator's parallel goal and R-HOOK-CONVERGENCE-20261004/R-N13. The experiment
owner supplied exact inputs; this audit did not import or execute its workers,
decode audio, load feature caches, run inference or feed references back into
discovery. Only this new note is written.

## Bound inputs and method

Experiment directory:
`artifacts/experiments/phrase-window-ablation/heldout-20261006T0030/`.
Bank directory: `artifacts/benchmarks/heldout-211-307-20261006T0020/`.

| JSON input | Verified SHA-256 |
| --- | --- |
| Bank `fixtures.json` | `3828ef756c3b2d36890e5b2f444c9323960ec9c0b358d02fe02a8c13ba89936b` |
| `run.json` | `70daeea8d916010e0629a871567eb54bf2589568f22cd3b09f07591aef61f94d` |
| `heldout-evaluation.json` | `060fa2a93a94e53aa6dced1b8122a492ec0121a760e5f5ca99cbc7dac3df76f3` |
| `common-reference-endpoints.json` | `c42363da2dbd3b362b0b2b6f9f88b200e7a3587a1e89c1da06f54b187f2886bc` |
| `filter-cap-disposition.json` | `c1909548d14c6fc56639113aabf0a3af1a23426d1326b89f2310236113e784a2` |

Read and rehashed these five JSON files, twelve prediction files bound by
`run.json`, and twelve truth JSON files bound by the bank: **29 files, each
under 1 MB, unchanged before/after**. Source identities, case/seed mapping and
frozen settings identity `f50e31ee…` agreed across receipts.

Every case has zero or one reference pair. An independent exhaustive oracle
computed interval intersection/union for both ordered recurrence spans,
required both IoUs to meet the threshold with the recorded 1e−12 tolerance,
and selected the eligible candidate with maximum mean IoU. It reproduced all
per-case match indices/scores at 0.5 and 0.75. Signed endpoint offsets were
recomputed from raw reference and selected prediction spans. Aggregate counts,
precision/recall/F1, negative counts, endpoint denominators and means matched
every saved all-case and per-seed field within 1e−12.

## Recomputed results

| Arm | TP/FP/FN at 0.5 | Precision / recall / F1 | Negative candidates | TP/FP/FN at 0.75 |
| --- | --- | --- | ---: | --- |
| A | 2/125/6 | 0.015748 / 0.25 / 0.029630 | 49 | 0/127/8 |
| B | 2/89/6 | 0.021978 / 0.25 / 0.040404 | 24 | 0/91/8 |
| C | 4/123/4 | 0.031496 / 0.50 / 0.059259 | 49 | 0/127/8 |
| D | 4/87/4 | 0.043956 / 0.50 / 0.080808 | 24 | 0/91/8 |

Seed211 A→D is 1/43/3→2/35/2; seed307 is 1/82/3→2/52/2.
There are eight reference pairs across eight positive cases and four negatives.
No arm supports accurate boundaries at the stricter threshold.

All **36 common-reference rows** reproduced exactly. B retains both A matches
and eight endpoints unchanged: mean absolute error 0.509974 seconds. C/D share
only seed307's legato pair with A: four endpoints, 0.561618→0.337583 seconds.
Seed211 has zero common C/D-versus-A pairs. The broader 0.509974→0.189230-second
comparison changes from two to four matched references, loses the control's
seed211 palm pair and gains other pairs; it cannot establish uniform endpoint
improvement. Endpoint fields inside both aggregate threshold rows explicitly
use the primary 0.5 matches, not nonexistent 0.75 matches.

All **12 disposition rows** reproduced from prediction decision records and
actual retained candidate indices. A's 127 candidates become B's 91 through
23 contrast exclusions plus 13 cap exclusions. All contrast exclusions occur
on missing-F0 negatives (4 seed211, 19 seed307). Negative reduction 49→24 is
23 contrast exclusions plus two cap exclusions; the other eleven capped
proposals are positive-case false proposals. Both sustained negatives still
retain ten false candidates each. Cap reduction is not discrimination evidence.

## Scope and route to root

Prediction JSON records no supplied inference reference and null detector/
boundary confidence; no candidate asserts a confirmed performance issue.
All prediction mtimes precede evaluation creation and the runner receipt binds
their hashes. This corroborates saved-file ordering; it does not independently
attest when a process first read truth or establish adversarial isolation.
Waveform/cache preservation and execution timing remain the owner's separate
receipts, rather than new claims from this JSON-only audit.

The [owner result note](2026-10-06-phrase-heldout-results.md) is quantitatively
supported with its stated denominator/filter caveats. Root may publish this
independent verdict as experimental evaluation evidence. Keep canonical
defaults unchanged; use fresh source/motif splits and equal caps for subsequent
precision work. Seeds 211/307 are consumed. Musician correctness, real-take
phrase accuracy and listening acceptance remain unverified.
