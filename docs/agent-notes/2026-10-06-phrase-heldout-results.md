# Frozen held-out phrase arm results

Actor `/root/phrase_dag`; authority root's explicit post-structural-bank
A/B/C/D execution release, operator's active parallel goal,
R-HOOK-CONVERGENCE-20261004/R-N13. Original recordings, canonical scripts,
registry and defaults remain unchanged. Neither seed211 nor307 was used to
select or retune settings. All predictions were saved/hash-bound before truth
files were opened.

## Source and exact receipts

| Receipt | SHA256 |
| --- | --- |
| Frozen bank index, `artifacts/benchmarks/heldout-211-307-20261006T0020/fixtures.json` | `3828ef756c3b2d36890e5b2f444c9323960ec9c0b358d02fe02a8c13ba89936b` |
| A/B/C/D harness | `78ca89de9cea327cc4ec1096a83522781a08bc161819699b69797ca273e2fb6c` |
| Frozen formula settings | `f50e31ee6eba0966580f78c9124938b4cdf116a6242eed2b0e7b2bb147f32edd` |
| Dated held-out orchestration source | `b8346d142f446bdfc4b5a58c3952d4aad3a4981048e7212da2264a25b71664aa` |
| Final `heldout-evaluation.json` | `060fa2a93a94e53aa6dced1b8122a492ec0121a760e5f5ca99cbc7dac3df76f3` |
| Final `run.json` | `70daeea8d916010e0629a871567eb54bf2589568f22cd3b09f07591aef61f94d` |
| Common-reference endpoint analysis | `c42363da2dbd3b362b0b2b6f9f88b200e7a3587a1e89c1da06f54b187f2886bc` |
| Filter-versus-cap disposition | `c1909548d14c6fc56639113aabf0a3af1a23426d1326b89f2310236113e784a2` |
| Source/cache/prediction re-verification | `139f942302eedd0a86d2b35db88be573f8a6d50cb0a82553eb74e4b2107497e1` |

Outputs are isolated under
`artifacts/experiments/phrase-window-ablation/heldout-20261006T0030/`.
The orchestration source is the durable dated companion
`2026-10-06-phrase-heldout-runner.py`; arm formulas remain in the previous freeze
receipt and `PHRASE_WINDOW_ABLATION_LANE.md`.

Twelve raw-mixture cases/120 seconds completed in **91.733 seconds**, with two
numerical threads and no timeout/failure. Child argv contain opaque `audio-NN`
and `case-NN` paths plus a source hash; no cohort, case ID, generator BPM, motif
length, reference or score label enters the analysis primitives. Environments
retain operational fields only. Generator IDs are used only by the parent to
bind receipts and later evaluate them; this is functional input separation,
not an adversarial filesystem sandbox.

Each case is decoded once through the unchanged16kHz FFmpeg rhythm decoder.
The same samples feed unchanged unseeded rhythm and phrase primitives. A
development-only check established byte-for-byte equality between the old
one-thread rhythm and two-thread phrase decodes of the same eight-second PCM
source. Current rhythm source matches its original pilot snapshot at
`264b723ca29e4731da0a12d5dce221e7826a38b67f848ce9f4ffcf8bfe4b35b9`;
phrase frontend remains `2ed031e8…`. The copied frontend's only change records
its feature cache. No pitch/model/frontend-compression job or whole dense
recording matrix was run. Fixed raw source/header extents, caches, predictions,
truth, bank index and frozen source identities were checked again afterward.

## Measured quality: no default adoption

Eight reference pairs exist across the positive cases. Four negative cases
declare no recurrence. Zero unsupported confirmed performance claims are emitted;
all candidates and refined endpoints remain hypotheses with null boundary/
detector confidence.

| Arm | TP / FP / FN at paired IoU0.5 | Precision | Recall | F1 | Negative false candidates | TP at IoU0.75 |
| --- | --- | --- | --- | --- | --- | --- |
| A short control | 2 / 125 / 6 | 0.0157 | 0.25 | 0.0296 | 49 | **0** |
| B contrast/ranking | 2 / 89 / 6 | 0.0220 | 0.25 | 0.0404 | 24 | **0** |
| C endpoint refinement | 4 / 123 / 4 | 0.0315 | 0.50 | 0.0593 | 49 | **0** |
| D combined | 4 / 87 / 4 | 0.0440 | 0.50 | 0.0808 | 24 | **0** |

At IoU0.75 all arms have eight false negatives. The control/combined false
positive counts at that stricter threshold are127/91. Relative gains do not
establish useful phrase accuracy: even D has87 false proposals and no stricter
matched pair. No canonical default is enabled by these measurements.

| Seed | A TP/FP/FN at0.5 | D TP/FP/FN at0.5 | A→D negative candidates |
| --- | --- | --- | --- |
| 211 | 1 / 43 / 3 | 2 / 35 / 2 | 15→10 |
| 307 | 1 / 82 / 3 | 2 / 52 / 2 | 34→14 |

## Matched-reference and filtering caveats

The broad matched-endpoint mean falls from0.510s (A, eight endpoints/two matched
pairs) to0.189s (C/D, sixteen endpoints/four matched pairs). **Those are different
reference sets.** C/D retain only one of A's two matched pairs, lose the seed211
palm pair, and gain seed211 timing-reference/errors plus seed307 palm. They do
not simply improve all control matches.

On identical common references, C/D versus A has only **one pair/four endpoints**,
all seed307: mean absolute error0.562s→0.338s. Seed211 has zero common-reference
endpoint samples, so its paired improvement is unknown. B retains both A pairs
and their eight endpoints unchanged. Coherent comparisons must preserve these
denominators and losses; aggregate mean reduction alone is not an endpoint win.
No arm yields accurate boundaries at IoU0.75.

The36 proposals removed by B comprise23 contrast-threshold exclusions and13
ranking-cap exclusions. All23 contrast exclusions are on missing-F0 negatives:
four seed211 and nineteen seed307. The cap removes two sustained-note negative
proposals and eleven positive-case false proposals. Thus negative49→24 is23
contrast exclusions plus two cap exclusions. A capped candidate list does not
prove improved acoustic discrimination. Both sustained negatives still produce
ten B/D false candidates each.

The preregistered relative recall/negative-count checks improve, but endpoint
comparison is sparse and swaps reference sets, while strict-quality evidence is
zero. This is an experimental result with limited gains and unresolved failure,
not production or musician acceptance. Both held-out seeds are now consumed;
further knob selection must not reuse them as fresh confirmation.

## Preservation and next action

The successful runner snapshots its sources, saves per-case stage stdout/stderr,
records owned child PID/argv, and has120second preemptive case/600second overall
deadlines. No signalling was required. All120seconds native sources retain their
original waveform hashes. Every case decodes to160000 mono analysis samples;
masters were not made or altered. Final all-prediction and evaluation receipts
are distinct. Later common-reference/filter audits read evidence only and run
no inference. Prototype orchestration is not an installed daemon or production
security boundary.

The specification records a next **metadata-only** false-positive experiment
with fresh seeds and equal ranking caps, temporal-order controls and identical
reference-set endpoint comparisons. It generates no audio or new predictions
and adopts no change. Root owns its future resource admission, implementation
assignment, evaluation release and tracker/publication facts.
