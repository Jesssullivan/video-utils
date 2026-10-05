# Completed synthetic calibration pilot — independent results receipt

Actor: `/root/audio_research`. Authority: the operator-approved parallel project
goal, repository `AGENTS.md`, R-HOOK-CONVERGENCE-20261004, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`, and R-N13. This lane owns this receipt
only. No workers, tests, recordings, rendered masters, sibling repositories or
tracker state were changed. The expensive pilot was not rerun.

## Result and exact evidence

Root's completed invocation returned exit 0. Its saved pilot reports
`completed_generated_calibration_pilot`, no failures, and **275.720009 seconds**.
All twelve raw-mixture discovery cases completed, covering the 120-second
generated bank. Four pitch jobs completed with 30 seconds aggregate coverage
(8+8+6+8) and 3,750 branch frames. Both generated-reference evaluations completed.
These are synthetic measurements, not actual-take accuracy or musician truth.

Bank: `artifacts/benchmarks/root-calibration-bank-20261005T2255/`.
Pilot: `artifacts/benchmarks/root-calibration-pilot-20261005T2300/`.

| Artifact | SHA256 |
| --- | --- |
| Bank `fixtures.json` | `3a6d117a50b32ad4f9e1b60921ee1b8a1d4376cc821ebcb31f14f4b8d80fdc73` |
| Pilot `pilot.json` | `4609ad355426ba957cbfc1fc860fe02a7514bb8430ca576c4dafc741f199248e` |
| `pitch-pilot-index.json` | `5c183df75f67dfa4b6d4a7b3c13b7d79d9fcbfa0408ce90d58a80017948ed343` |
| `phrase-pilot-index.json` | `38d79d8e744ad8a4e43699a1da810d42d291b616c25afb70ba7a94522b0121bf` |
| `evaluation-pitch/pitch-calibration.json` | `fcecba70e9945480080e205647fbf1d622e5938a1a4682987184e9e5d391fc54` |
| `evaluation-phrases/phrase-evaluation.json` | `5a105dc9a22d6ebb5648dcf4f17460ec6bcda693afe3c9049d99aba0dfec92e9` |

Independent verification covered 108 truth/component hash and native WAV-header
checks, all twelve cases/120 seconds, and 176 generated events with unique IDs
and consistent native-sample/source-time onset axes. Null observed onsets remain
null for omissions. All nine new cases declare complete generated scores; three
legacy cases retain partial attack-only score status. Rendered component sums
were independently checked at 5,760,000 native PCM16 sample positions: mixture
minus clean/click/noise differs by at most one LSB, within the declared two-LSB
quantization bound. Nine declared click-only intervals have exactly zero rendered
clean and noise samples. This samplewise audit interpreted fixture PCM values;
the evaluator workers separately declare hash/header reads without decoding or
inference.

All nine source snapshots match their saved SHA256 and the frozen repository
source at inspection; all 28 original input identities remain valid. Each opaque
discovery WAV alias is byte-identical to an original component. Evaluator outputs
bind the exact bank and pilot-index hashes above. The frozen evaluators were
called again **in memory**, reading existing evidence only: all per-case metrics,
aggregate metrics, quality alerts, counts and gate dispositions match the saved
results. Independent arithmetic also recomputed aggregate pitch numerators and
denominators and phrase micro TP/FP/FN sums. No inference, resynthesis, media
processing or artifact writes occurred during this recomputation.

## Discovery isolation and acceptance scope

All twelve discovery runs are unseeded: `tempo_seed: null` and
`reference_grid_supplied: false`; observed worker argv contain neither `--bpm`
nor expected-rhythm references. Byte-identical inputs use opaque names and
generic sample-zero manifests. Semantic fixture IDs, component labels, intended
pitch/score, attack truth, phrase boundaries and warps are absent from discovery
argv/manifests. Child environments retain operational variables only. Generated
labels enter the standalone evaluators after discovery artifacts are saved.
This is input isolation, not an adversarial filesystem sandbox.

Both evaluators report **zero unsupported confirmed claims and zero failed
evaluated hard gates**. Pitch reports `completed_with_regression_alerts`; phrase
reports `generated_fixture_calibration`. Listening acceptance remains false.
Successful execution and integrity checks do not imply successful phrase
detection, repaired performance, recovered isolated stems, real-note correctness,
time-signature identification, or AU/Logic host acceptance.

## Measured quality

| Measure | Actual result | Scope |
| --- | --- | --- |
| Boundary matching, 50 ms | TP 5, FP 29, FN 31; micro F1 **0.14285714285714285** | Generated phrase-boundary references; macro F1 0.11375661375661375 across 12 applicable cases |
| Recurrence matching, IoU 0.5 | TP **0**, FP **4**, FN **5**; micro F1 0 | Seven macro-applicable cases; five both-empty cases have null per-case scores |
| Matched recurrence alignment evaluations | **0** | No actual-bank alignment measures generated warp/shift accuracy |
| High-register raw pitch accuracy | **319/319 = 1.0** | Eligible stable monophonic frames only |
| Low-register raw pitch accuracy | **745/745 = 1.0** | Eligible stable monophonic frames only |
| Pitch regression alerts | **2 alerts**, affecting 3 high-register false-voiced frames | One tuning-ladder silence frame; two legato-transition silence frames |

The pitch denominator is not all 3,750 branch frames. Excerpt edges, transition
crossings, polyphony and branch range exclusions remain explicit. A low-register
branch has 749 transition-crossing frames; the high-register branch has 914
out-of-range frames. Eligible-frame accuracy on controlled harmonic proxies
does not establish accuracy on the operator's distorted recording or arbitrary
glides/sweeps. Voicing probability remains algorithm evidence, not note-correctness
confidence.

The four false recurrence candidates occur on sustained low32, missing-F0 and
timing-reference cases. All five declared recurrence pairs remain unmatched.
The corrected DTW partial-coverage/absorption rule passed independent toy tests
in the companion contract review; this pilot did not exercise a successful
generated-pair alignment. No warp-accuracy or injected-error-detection success
should be inferred from its completed comparator stages.

## Diagnostic clue and next-week priorities

Existing artifacts show a concrete half-time/window mismatch. Palm-muted and
legato recurrence cases choose approximately **88.995 BPM**, or 0.674196 seconds
per pulse. Their declared repeated motifs last 1.348315 seconds. Current recurrence
search considers only 4/8/16 pulses, making its shortest window approximately
2.696783 seconds, twice the motif length. Timing-reference/errors choose about
89.005 BPM and use similarly doubled windows; the two timing-reference candidates
do not match both generated regions at IoU 0.5. This is an observed mismatch and
a plausible failure mechanism, not an isolated causal experiment. Forcing the
generator's 178 BPM into discovery would invalidate the default unseeded task.

For seven days at 5–10 development hours per day (35–70 hours), prioritize the
offline phrase pipeline before expanding correctness claims or plugin packaging:

| Day | Priority and reviewable result |
| --- | --- |
| 1 | Freeze this baseline and inspect candidate search coverage, half/double-time choices and failures per case. Declare reference-versus-discovery experiments explicitly and prepare withheld generated variants. |
| 2 | Compare multiple pulse/subdivision and seconds-domain motif-length hypotheses, including short motifs. Preserve unknown tempo and variable-tempo behavior; labels remain excluded from search. |
| 3 | Refine phrase endpoints using acoustic evidence at finer resolution than pulse quantization. Compare attack, low-register spectral and texture features while preserving intentional 32 Hz content. |
| 4 | Run frozen unseeded recurrence evaluation on development and withheld variants. Report full TP/FP/FN, null applicability, candidate budget and coverage; investigate sustained-note false recurrences. |
| 5 | Once genuinely discovered pairs match, measure raw timing differences and bounded DTW on generated shifts, omissions and additions. Report affected-landmark coverage, raw offsets and warped residuals separately. |
| 6 | Review sparse source-bound annotations and A/B exports on the actual take. Retain ambiguity for click/pick overlap, octave errors, tuplets and polyphony; observations require listening and musical context. |
| 7 | Consolidate `just`/Rust interfaces, reports and review markers with documented limits. Keep an AU bridge prototype scoped to bounded DSP/interfaces; Logic installation/host acceptance remains a separate milestone. |

Improving this fixed bank alone is insufficient: reserve held-out conditions and
retain reference-free inference. Before advertising musical-error analysis,
require successful discovered-pair coverage and measured timing/edit behavior,
then separate human-reviewed real-recording evidence. Existing source scores do
not qualify those claims.

Disposition: this completed pilot is reproducible experimental evidence with
weak structural-detection quality clearly exposed. No blocking integrity or
unsupported-claim regression was found. Companion design/source review:
`docs/agent-notes/2026-10-05-calibration-contract-review.md`.
