# Independent calibration contract review

Actor: `/root/audio_research`. Authority: the operator's parallel project goal,
repository `AGENTS.md`, R-HOOK-CONVERGENCE-20261004, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`, and R-N13. Ownership is limited to this
receipt. Workers, tests, source recordings, rendered masters, shared board and
tracker state were not edited by this review lane.

Review started with `BENCHMARK_CALIBRATION_LANE.md`,
`PITCH_CALIBRATION_LANE.md`, `PHRASE_CALIBRATION_LANE.md`, the evaluator hook
contract and composite pilot contract. This is a design and evolving-source
review, not a receipt of the complete generated pilot or actual-take acceptance.

## Findings and disposition

1. **Tempo conditioning and budget mismatch — corrected in pilot design.** The
   initial composite contract supplied 178 BPM to every mixture and allowed
   wording consistent with 30 seconds per pitch job. Root corrected this before
   implementation: discovery is unseeded throughout the bank, including the
   variable-tempo case; four pitch jobs total 30 seconds (8+8+6+8). The revised
   pilot specification was read back. Root also requires the technical-v2
   benchmark runner to omit BPM seeds by default. Its source fix was read back:
   every v2 case has empty BPM arguments and no truth-derived click template;
   historical v1 behavior is separate.
2. **Rendered missing fundamental — implemented bounded verification.** The
   new generator jointly fits sine/cosine coefficients for F0 and harmonics
   2, 3, 4, 5 and 7 on rendered PCM16, seconds 1–7. A stride of 24 gives 2 kHz
   analysis sampling, above twice the highest fitted harmonic. F0 amplitude
   must be below 0.00005; each declared harmonic amplitude must agree within
   0.00005. This is a measurable absence bound in a synthetic harmonic proxy,
   not mathematical zero or proof about an amplifier or real guitar. No
   nonlinear stage follows synthesis of this case. Its absent-F0 preservation
   metric is null rather than dividing by nonexistent reference energy.
3. **Pitch metric construction — implementation supports the contract.** The
   evaluator independently reconstructs frame centers, branch frame sizes,
   clipped window extents and edge completeness. Stable monophonic eligibility
   requires complete context within one reference region. Raw accuracy includes
   voiced-reference abstentions in the denominator; octave and chroma metrics
   remain distinct. Both branches are evaluated without selecting the better
   branch using truth. Transition scans retain possible negative centered-window
   lookahead bias; unsupported window resolution and target range are separate
   statuses. Branch/condition aggregates use summed frame evidence, and pitch
   p95 remains null below 20 observations. Recursive unsupported-claim detection
   was added and read back; unsupported claims retain a durable failed-gate
   receipt and cause exit status 1.
4. **Phrase attack metrics — corrected in source.** The initial fallback missed
   the actual `broadband_attack_candidate` event kind. It also skipped false
   positives when a labeled reference contained no picked events. Current
   source includes that kind, distinguishes known empty attack references from
   unknown ones, and preserves the legacy attack-only reference status.
5. **Phrase aggregates — corrected in source.** Initial output aggregated only
   boundaries. Current source aggregates attacks, recurrence pairs and phrase
   spans too, with micro TP/FP/FN sums and macro means over applicable scores.
   Hierarchy levels remain separate. Phrase p95 is explicitly a descriptive
   nearest-rank sample quantile with its sample count; unlike the pitch policy,
   it is not suppressed at small N and makes no confidence claim. The published
   one-empty-set score-zero convention is explicit; both-empty scores are null.
6. **Raw versus warped timing — retained.** Phrase alignment evaluates only
   covered generated landmarks without extrapolation, preserves unwarped offsets
   alongside warped residuals, and labels timing changes absorbed by DTW. A small
   residual does not establish an unchanged performance or a musician mistake.
7. **Generator provenance and fixture attacks — corrected in source.** The
   new bank initially parsed the instrument registry separately from the bytes
   hashed for its receipt; configuration metadata had an analogous binding
   concern. Current source parses and hashes the same registry/configuration
   bytes, checks supplied parsed configuration equality, and hashes the legacy
   generator dependency explicitly. The ladder starts independently enveloped
   clean and distorted segments within each note: all nine midpoint envelope/
   phase resets now have explicit generator-condition-transition nuisance labels.
   Pick-detection scores remain selected against generated picked events; they
   are not generic acoustic-transient completeness scores.
8. **Hard integrity gates — corrected in source.** The contract distinguishes
   strong 32 Hz damage and bypass alteration from ordinary quality baselines.
   Initial technical-v2 source recorded low-frequency damage as only a quality
   alert. Current source records explicit source, extent, low32 and bypass gate
   dispositions, and failed evaluated gates make a case/suite fail. Protected
   click attenuation is explicitly `not_evaluated` because attenuation is never
   requested. The initial bypass identity gate allowed one PCM16 LSB rather than
   exact identity. Final source now requires exact zero error on the denoised,
   pre-normalization samples, records `absolute_tolerance: 0.0`, and separately
   retains presentation normalization. Cross-worker revision failure also
   contributes to the suite's hard failure count.
9. **DTW absorption under partial coverage — corrected and independently verified.**
   An independent toy reference with source landmarks `[0,1,2]` and target
   landmarks `[3,4,4.8]`, compared against a path covering only unchanged
   `(0,3)` to `(0.5,3.5)`, yields coverage 1/3 and zero residual. Initial source
   nevertheless claimed the generated 200 ms late change was absorbed by DTW.
   Its change test used all reference landmarks while residuals used only
   covered landmarks. Absorption must require a changed landmark actually
   covered, or a changed-rate interval with both endpoints covered, and retain
   affected coverage/unknown status when the path covers only an unchanged
   prefix. Final source implements that requirement. Independent re-execution
   of the original counterexample now returns false absorption and
   `unknown_generated_change_outside_path_support`, with zero changed landmarks
   or intervals covered. A complete path through the same changed landmarks
   returns a qualified `covered_change_absorption_diagnostic`. Producer-detected
   raw attack offsets and warped residuals are also retained separately from
   generated renderer-operation context.

## Independent arithmetic evidence

With bytecode writing disabled, 150 deterministic small random timestamp cases
were checked against exhaustive enumeration of all feasible one-to-one matches.
Both the technical-v2 ordered matcher and phrase min-cost matcher agreed on
maximum cardinality and, secondarily, minimum total absolute error. Empty sets
were included. The independent oracle did not reuse either matching algorithm.
This validates bounded matching arithmetic; it does not validate event labels,
waveform realism, full pilot provenance or real-recording detections.

Independent pitch toy oracles also passed: a true-voiced abstention remains in
raw pitch/chroma/voicing denominators; a +1200-cent estimate is chroma-correct
but raw-pitch-wrong; known silent false voicing is retained; small-N p95 is null;
two nested confirmed-note/musical-error claims are detected; and the transition
scan retains a deliberately constructed -104 ms centered-window lookahead bias.

The first actual generated bank at
`artifacts/benchmarks/technical-v2-bank-first/fixtures.json` has index SHA256
`0787f66631238c6aff089fe06d3b6fc34856689975826bfa4ba53a766784cf64`.
This lane independently checked all twelve cases totaling 120 seconds:
108/108 truth SHA256, component SHA256 and native WAV-header checks passed.
Every per-case helper/legacy generator, configuration and instrument registry
hash matched current source at inspection. The ladder contains nine explicit
condition-transition labels. These are actual generated-file checks, separate
from the earlier arithmetic tests and the upcoming full discovery pilot.
The benchmark runner then received the exact-bypass/tally correction, so the
first bank's legacy-runner hash is a preserved historical binding, not a claim
that it matches the final runner. Root will generate a fresh bank for final
pilot evidence.

Root's fresh bank
`artifacts/benchmarks/root-calibration-bank-20261005T2255/fixtures.json` has exact
SHA256 `3a6d117a50b32ad4f9e1b60921ee1b8a1d4376cc821ebcb31f14f4b8d80fdc73`.
This lane independently repeated all 108 hash/native-header checks and checked
176 generated events for unique IDs and consistent native-sample/source-second
onset axes, including null observed onsets for omissions. All nine new cases
declare `complete_generated_score` and a known attack reference; the three legacy
cases remain explicitly partial attack-only scores. The fresh bank binds the
final runner `9b8dc2a8…` and unchanged helper/configuration/registry sources.
An additional independent samplewise check interpreted all 5,760,000 native
PCM16 sample positions: rendered mixture minus rendered clean, click and noise
components differs by at most one PCM16 LSB, within the declared two-LSB bound.
All nine new-case click-only template intervals have exactly zero rendered clean
and noise samples. This audit did interpret fixture PCM values; the evaluators'
own `source_audio_decoded: false` declaration refers to their separate hash/header
verification and must not be generalized to this audit's samplewise check.

Final source checkpoint hashes read back:

| File | SHA256 |
| --- | --- |
| `scripts/benchmark.py` | `9b8dc2a8aea58fcabf0fe74dfb3cfc967319e0a060a44ba7c40d6e57aa4c1656` |
| `scripts/benchmark_bank.py` | `087a67c009bb48abeac78259fc2719c02886e81b956ef8a9c62a22e6ee3913d5` |
| `program/benchmarks-v2.json` | `94fe5085f641c430b579d038736b9036962abfabec8bad86dea0ba163ce245ab` |
| `scripts/pitch_evaluate.py` | `a91ce8e9386cc7c63c5a5d53b8233f2c46a1f42fdd06ab1ae0eea3dc83405805` |
| `scripts/phrase_evaluate.py` | `3e503de277b2fd233fe802595a09a655c89669b0eb820f228e677c1b94b828a5` |
| `scripts/calibration_pilot.py` | `d7cfc0cf96cbefc4ba14a60b8d8f39427b7bf5acab7080e47a0a4fbe90b7e15f` |

The design agrees with the distinctions in primary references:
[librosa pYIN](https://librosa.org/doc/0.11.0/generated/librosa.pyin.html)
documents centered analysis and voicing outputs;
[mir_eval melody](https://mir-eval.readthedocs.io/latest/api/melody.html)
separates voicing, raw pitch and chroma metrics; and
[mir_eval segmentation](https://mir-eval.readthedocs.io/latest/api/segment.html)
documents boundary matching. These references do not make generated labels
musician truth and do not prescribe this project's explicit small-N policies.

## Publication boundary

The first bank is verified as described above. The composite pilot source now
uses byte-identical opaque audio aliases and generic sample-zero manifests;
case IDs, component class, attacks, pitch, score, boundaries and warp labels
are absent from discovery argv/manifests. It strips nonoperational environment
variables for child invocations, completes discovery before evaluator launches,
and preserves failed stages/partial indices. This is an input-isolation contract,
not a filesystem sandbox or adversarial blindness proof. At the initial source
review, discovery, four actual pitch jobs and complete evaluator subprocess
receipts were pending; their final verification is recorded below. Publication
must distinguish source review, exact pilot indices, outputs and gate results. No listening
approval, AU validation or actual-take musical-error acceptance follows.

Disposition: no unresolved blocking defect in the reviewed source/contracts.
Full pilot completion and repository test-suite acceptance are not asserted by
the source-only portion of this receipt; actual pilot verification follows.

## Final actual pilot verification

Read-only inspection of
`artifacts/benchmarks/root-calibration-pilot-20261005T2300/pilot.json` verified
`completed_generated_calibration_pilot`, no failures, 275.720009 seconds,
twelve completed discovery cases and four completed pitch jobs totaling
30 seconds and 3,750 branch frames. All nine source snapshots match their
receipt hashes and current repository source; all 28 original input hashes
remain valid; every opaque WAV alias has the hash of an original component.
All observed discovery argv omit BPM/expected-rhythm references and semantic
fixture IDs. Exact pitch/phrase pilot indices and fresh bank hashes agree with
their evaluator results. The evaluators declare no inference, zero unsupported
claims and passed evaluated hard gates. This lane independently recomputed
pitch aggregate numerators/denominators and phrase boundary, attack and
recurrence micro TP/FP/FN sums from per-case results.

| Final artifact | SHA256 |
| --- | --- |
| `pilot.json` | `4609ad355426ba957cbfc1fc860fe02a7514bb8430ca576c4dafc741f199248e` |
| `evaluation-pitch/pitch-calibration.json` | `fcecba70e9945480080e205647fbf1d622e5938a1a4682987184e9e5d391fc54` |
| `evaluation-phrases/phrase-evaluation.json` | `5a105dc9a22d6ebb5648dcf4f17460ec6bcda693afe3c9049d99aba0dfec92e9` |

Quality remains a visible experimental baseline. Pitch reports two regression
alerts: one high-register false-voiced frame in the tuning ladder and two in the
legato transition. Raw pitch accuracy is 1.0 on only the eligible controlled
monophonic frames: 319 high-register and 745 low-register frames, out of 3,750
branch frames overall. This does not imply perfect pitch identification for
every frame, polyphony, octave ambiguity or real guitar. Phrase boundary matching
at 50 ms yields micro TP=5, FP=29, FN=31, F1=0.14285714285714285. Recurrence
matching at IoU 0.5 yields TP=0, FP=4, FN=5, and no generated recurrence receives
a matched alignment evaluation. Structural discovery is weak in this bank and
should not be advertised as calibrated musician-error grading. The corrected
partial-coverage diagnostic is verified by the independent toy oracle, not by
a successful actual-bank alignment that did not occur.

Final disposition: no blocking provenance, arithmetic or unsupported-claim
regression found in the completed generated pilot. Experimental evidence is
publishable with the quality and scope qualifications above. This receipt does
not attest repository-wide test completion, actual-take listening acceptance,
definite missed/rushed notes, recovered stems or Logic/AU host acceptance.
