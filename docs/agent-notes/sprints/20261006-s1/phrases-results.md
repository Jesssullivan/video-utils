# S1 heldout phrase-proposal result

Actor `/root/s1_phrases`; authority operator six-lane S1 request and
R-HOOK-CONVERGENCE-20261004/R-N11/R-N12/R-N13. Root released exactly one numerical
run with worker38b736543a83d5c706a8803014f4e308685eee2c84275e9e6768c431b6b8d0e3,
plan dd4c43532f47273948e23a3a35e93e61fa8a576ec0f32662036b39fe6b432a6c and release
6289ebf4276a46d69497cad0868f9adb3630fc972de638d9a3d9d6cd69c9196d.
The earlier source8f40 was repaired before audio generation solely to refuse
blocking FIFO metadata; arms/settings/plan were unchanged. The final16 targeted
source-only tests passed. No heldout thresholds were changed after results.

One900s externally bounded job ended exit0 in69.951356s, with all12 source jobs
below120s (maximum7.498848s),2 numeric threads, no signals or restarts. Exec3711
and owned numericalPID/PGID11602 are terminal. Native48000Hz mono PCM16 clips
were decoded to exactly128000 analysis samples per8s source. All12 predictions
were globally sealed before scoring opened any truth. Source/default catalog,
accepted movie/master and Desktop export were not changed.

## Measured generated-fixture outcome

The12 cases are new seeds1301/1423 × six cohorts. They contain4 full generated
recurrence-pair references,16 typed endpoints and8 known-negative cases.
All references, including baseline abstentions, remain in denominators.

| Arm | Predicted pairs | TP/4 at both-spanIoU0.5 | TP/4 at both-spanIoU0.75 | False candidates in8 negative cases |
| --- | ---: | ---: | ---: | ---: |
| Araw frozen raw2/4/8/16-pulse baseline | 6 | 1 | 0 | 2 |
| S1_support single0.24s activity gap | 4 | 4 | 4 | 0 |
| S2_multiscale0.12/0.24/0.40s gaps | 4 | 4 | 4 | 0 |

Araw's total TP/FP/FN atIoU0.5 is1/5/3 and at0.75 is0/6/4. The negative-only
false-candidate count2 is a separate denominator, not its total FP count.
The two treatment arms have TP/FP/FN4/0/0 at both thresholds on this fixture
family. Per-cohort negative counts(Araw→S1/S2) are low32-sustain1→0,
missing-F0-sustain1→0, ordered-click-only0→0 and fan-only0→0, each across two
cases. Null recall for negative-only cases does not imply complete specificity.

Araw matched0/16 typed endpoints at20,50 or100ms. Both new arms matched0/16 at
20ms,4/16 at50ms and16/16 at100ms. Their matched-pair endpoint MAE is
0.073671875s over16 endpoints. Araw MAE is0.288969099s over the four endpoints of
its soleIoU0.5 match, and null at0.75; these unequal match sets do not support a
common-reference MAE reduction claim. The centered256ms FFT support and16ms hop
remain explicit; no sub-frame precision or musical-error judgment is established.
S2 andS1 are identical on these cases, so there is no measured multiscale benefit.

## Evidence and limitations

* Bank `artifacts/experiments/s1-phrases/bank-1301-1423/bank.json`:
  41060b177358523628fa9d32ddf5573b422d1e73f86f2a38c167c1a646c56786.
* Globalseal `run-1301-1423/predictions-sealed.json`:
  eb9dfd588cd3b4c632c18ebd6c0397086459710d92a4b6e65d6ed741a1c47955.
* Raw evaluation and durable `phrases-evaluation-1301-1423.json`:
  12aa258d24511621cd63a2b2d9779de510c93d17538d5964b3cb4cbadf531749.
* `phrases-frozen-evidence.json`:
  3c137c7fe5c1fc28be77923041ee34270acfcfb9fdbae9f004cb136cd6986d65;
  preserves26 exact rawJSON documents with hashes for future metric readback.
* `phrases-numerical-start.json`/`phrases-numerical-end.json` preserve owned run
  identity, root authority, exact source/plan/release, elapsed time and no signals.

The improved pair coverage is restricted to **synthetic repeated motifs separated
by quiet gaps**. These two seeds vary geometry and nuisance realization within
an existing recipe family. They do not establish proposals inside continuous
back-to-back riffs, a central challenge in the actual practice video. Real fan
collisions, different distortion/capture responses, varying phrase lengths,
subdivisions, errors, full-band content, stereo and physical-technique labels
remain untested. Four positive pairs are insufficient to calibrate confidence
or estimate a population success rate. Sustain negatives intentionally contain
music yet no generated riff references; rejection does not mean32Hz notes were
removed or do not matter. Source audio is analyzed without restoration filtering.
The20th-percentile activity floor can contain musical content when most of a
clip is guitar; it is an observed feature baseline, never an approved pure-noise
capture. Such high-occupancy cases are not covered by this separated-motif bank.

There is no default adoption, new advertised MCP product tool, confirmed musical
mistake, detected-note score, real-demo inference or listening acceptance.
A future preregistration should include contiguous repeats and partial/changed
phrases without quiet delimiters, plus heldout real source-bound annotations.
This completed pilot is a bounded upstream-coverage result; the accepted demo
and original automatic baseline remain intact. Independent metric/component
verification is assigned to `/root/s1_audit` and will be recorded separately.
