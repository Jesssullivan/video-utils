# Phrase temporal-order experiment: implementation/source-test freeze

Authority: parent/root admitted implementation and source tests only on October6,
2026; operator parallel project authorization and R-HOOK-CONVERGENCE-20261004 /
R-N13. Audio generation and discovery have **not** been released or executed.
Canonical sources, the consumed211/307 bank, frozen A/B/C/D harness and results
remain unchanged. Publication belongs to root.

| Frozen item | SHA256 |
| --- | --- |
| [New generator/runner/source tests](2026-10-06-phrase-order-null.py) | `5582a5cf2b415b07a434b59f407da8c6e63fa9101001267dbba03f0cabe9f066` |
| [Closed settings](2026-10-06-phrase-order-null-settings.json) | `232f7503f58e9ebcb2b59b220b97755b7001683eccd80893634d8f6b777079a3` |
| Metadata-only `artifacts/experiments/phrase-window-ablation/order-null-prereg-20261006T0149/plan.json` | `15c04b2f846da264c9f8d758e9bba8ba5a90a466a30755c75ec0d9922e2be652` |
| Original A/B/C/D harness, unmodified | `78ca89de9cea327cc4ec1096a83522781a08bc161819699b69797ca273e2fb6c` |
| Canonical feature frontend/search, unmodified | `2ed031e8000cbcda92b504db10c98de03f456c90573cbff815cbb940c9ac86fe` |
| Canonical rhythm worker, unmodified | `264b723ca29e4731da0a12d5dce221e7826a38b67f848ce9f4ffcf8bfe4b35b9` |

## Fixed construction and inference separation

Seeds419/523 each have five8-second native48kHz mono PCM16 cases: low32 sustain,
missing-fundamental sustain, click/noise-only, palm recurrence and legato
recurrence. Ten clips/80seconds; six declared negative and four generated
positive cases. Metadata freezes deterministic SHA256-derived motif placement,
duration/gain/drive and independent click/fan/noise parameters. All five cohorts
for a seed share the **exact** nuisance component recipe; neither silence nor
click absence distinguishes the positive cases. Fan/noise levels vary over the
complete clip including the opening. These are synthetic nuisance constructions,
not a measured model of Jess's box fan.

Low32 and positive guitar constructions use musical-only tanh before additive
mixing. The missing-F0 clean signal is a **linear** sum of harmonics2/3/4/5/7 of
C1 (32.7031956626Hz); no saturation is applied to that sum. Future generation
reopens saved clean PCM and jointly fits DC and sine/cosine harmonics1–7 over
seconds2–6, requiring fundamental amplitude≤5e-5. The fit establishes the clean
generated component's construction only. Saved four-component WAV headers and
integer additivity are checked; independently rounding three PCM components
allows at most twoLSB summed error. No peak normalization conceals clipping.

The isolated runner copies pinned rhythm/frontend sources and inserts only the
previously used cache capture. One16kHz analysis decode per opaque audio-NN.wav
feeds unseeded rhythm and unchanged feature extraction. No generated BPM, seed,
cohort, motif span or score is passed in child argv or to analysis primitives.
Missing pulse evidence yields empty-arm predictions with explicit abstention.
Every prediction is saved and hash-bound before the evaluator opens any truth
JSON; all settings remain fixed afterward. This is an auditable process claim,
not adversarial filesystem attestation.

## Exact comparison and gates

Both arms use identical frozen A proposals:2/4/8/16 inferred pulses, original
cosine .8 search/deduplication and60-proposal cap. Feature standardization and
competitor baselines use the frozen original harness. `Bcontrol` equals original
B, with competitor contrast≥.10. `Border` additionally requires true cosine
minus the median cosine of cyclic rotations of **only the second** L-frame
window by offsets1…L−1 to be≥.10. Arithmetic tolerance is1e-12. The first window
is fixed; rotating both equally preserves dot products and is explicitly tested
as the wrong null. Zero-norm evidence abstains.

Each arm filters the full identical A universe, then uses exactly the same
descending competitor-contrast/cosine and ascending first-start/second-start/
length/original-index ranking with cap10. Order margin never reranks survivors.
Preserve per-proposal contrast, every rotated cosine, order baseline/margin,
qualification and separate threshold/cap dispositions. `Border` can retain an
A candidate below control's cap, so its final capped set need not be a subset
of the final control set. Homogeneous or repetitive guitar can lose valid
recurrences; temporally ordered clicks can survive. This guard is not an
instrument classifier or a confidence probability.

Evaluate identical full reference sets at pair-IoU .5/.75 per case, seed and
aggregate. Keep all false negatives and unmatched reference IDs. Compare signed
endpoint errors only on common reference-pair intersections, with explicit Ns,
lost/gained reference IDs and null mean errors for empty intersections. Split
negative false candidates into sustain/missing-F0/click-only cohorts. Both seed
primary-IoU negative counts must strictly improve without recall falling for a
relative research gain; this never establishes useful absolute accuracy or
musician acceptance. Unknown detector/boundary confidence stays null; any
confirmed-mistake claim or cap violation rejects evaluation.

Bounds: sequential workers, two numerical threads,120seconds/case and600seconds
overall. Only each just-spawned child may be signalled after a live poll under
R-N11, with an ownership receipt. Failed cases retain partial records and leave
truth unopened. Generator deadline120seconds; feature archive expansion≤1MB,
four exact NPZ members,≤1000 native feature frames/256 aggregated frames,
≤60 proposals/10 retained pairs per arm. JSON≤20MB, source WAV≤1MB. No pitch
jobs, downloads, networking, GPU jobs, master changes or canonical activation.

## Source verification and next stage

Final ten source tests PASS in3.193seconds. Tests cover an independently
computed cyclic cosine example, homogeneous abstention, equal caps/tie order,
exact original-B equivalence, fixed metadata/nuisance sharing, finite/cache/path
guards, native event arithmetic, explicit full-reference FN/common-intersection
nulls and rejection of confirmed claims. Tiny1000Hz in-memory algebraic renderer
arrays exercise native-axis and linear missing-F0 construction; **no new48kHz
bank waveform was created, saved or scored**, and no audio primitive or model
ran. A first test incorrectly used macOS's `/var` temporary alias; resolving
the test-owned root corrected it without relaxing symlink rejection.

Held commands after root's exact numerical release:

```sh
.venv/bin/python docs/agent-notes/2026-10-06-phrase-order-null.py --generate \
  --plan artifacts/experiments/phrase-window-ablation/order-null-prereg-20261006T0149/plan.json \
  --output artifacts/experiments/phrase-window-ablation/NEW-BANK

.venv/bin/python docs/agent-notes/2026-10-06-phrase-order-null.py \
  --bank-index artifacts/experiments/phrase-window-ablation/NEW-BANK/fixtures.json \
  --bank-sha256 EXACT-GENERATED-INDEX-SHA256 \
  --output artifacts/experiments/phrase-window-ablation/NEW-PREDICTIONS
```

Root should admit the frozen source/settings/plan, release generation, inspect
construction receipts, then release exact-index inference/evaluation. Independent
read-only review is assigned separately. No quality result or default adoption
is established by this source-test checkpoint.

## Independent review amendments before numerical release

The initial44890c source /967a7 settings /48c674 plan candidate had eight passing
source tests but four admission gaps. Independent review requested executable
preflight, owned descendant cleanup, whole-run budgets and evaluator/integrity
pins. The original0129 metadata plan is retained; it is superseded rather than
overwritten. The final0149 metadata plan above binds the amended source.

Closed settings now bind exact Nix FFmpeg/FFprobe paths, executable file hashes
and8.1.2 version prefixes. Before discovery decoding, each executable must be present,
executable, hash-consistent and pass a five-second `-version` check under the
closed worker environment; version stdout/stderr caps are64KiB. The actual media
version preflight has not run during source-only authorization. Runtime records
first lines and version-output hashes. Historical metadata no longer supplies
unpinned executable strings. The evaluator/parser source is pinned before import
to3e503de277b2fd233fe802595a09a655c89669b0eb820f228e677c1b94b828a5.

Each worker/preflight Popen owns a new session/group. Cleanup probes that exact
owned PGID even after leader exit; live descendants receive TERM and, if still
live, KILL. A fresh group probe, leader poll and R-N11 ownership receipt accompany
the action; unverified cleanup fails the run. Source tests mock these operations
and prove exited-leader cleanup without signalling any process.

The600-second budget starts at runner entry, including native validation, copies,
preflight, decoding, scoring and sealing. Deadline checks surround truth access,
evaluation and final receipts. Immediately before truth and again after scoring,
verify canonical/copied sources, evaluator, settings, instrument context, original
and opaque source bytes, analysis/cache files and every prediction receipt.
A callback records truth_opened only inside an actual successful truth-file open,
so early path/setup/hash failures preserve the unopened state. Later failures
retain an explicit opened state and cannot leave a success-status run receipt.
The generated truth admits at most one reference pair per case.

The two added source tests cover exited-leader group ownership/deadline behavior
and executable/evaluator/instrument/copied-artifact pins. These amendments do
not change the contrast, order null, ranking, cap, generator recipes or metrics.
Independent final source admission remains a separate review artifact. No new
48kHz bank waveform or audio primitive/model inference has run.
