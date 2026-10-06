# Phrase localization: consumed-case coordinate diagnostic

Authority: root assigned read-only localization error analysis and a new plan;
operator parallel project goal, AGENTS.md, R-HOOK-CONVERGENCE-20261004/R-N13.
This is **post hoc analysis of consumed419/523 data**, not untouched confirmation
or a new discovery run. No waveform was decoded, feature extracted, proposal
search rerun, alternative boundary prediction generated or threshold tuned.

Inspected immutable inputs: bank42ff7501, runcc3a66cd, evaluationcc3e28ce,
disposition auditcbdd8d88 under the previously recorded order-null bank/run
directories. The frozen source5582a5cf and canonical feature2ed031e8 were read.
Saved NPZ time arrays/layout metadata were inspected; their feature values were
not used to rerun similarity or alignment. The independent numerical review
separately reproduces existing pair scores and metrics; this note investigates
representation and coordinate limitations.

## Clock checks and actual coordinates

All four positive cases have26×501 cached features, frame-center times0…8seconds
at256/16000 = **16ms** intervals (maximum floating hop error8.743e-16s). Native
source384000/48000 and decoded128000/16000 both equal8s, with generated source
origin0. Every retained candidate start exactly equals `origin + integer*period`;
maximum arithmetic error is zero. All pulse bins are populated: full bins have
19–24 frames, and final partial bins have4–18. Consequently the `continue` for
empty bins cannot cause an index-compression shift in these cases.

The source uses a4096-sample **256ms** centered STFT. For centered frames, the
librosa frame time belongs at `frame*hop/rate`; adding another128ms half-window
offset would be incorrect. [Official STFT documentation](https://librosa.org/doc/0.11.0/generated/librosa.stft.html)
and [frame conversion documentation](https://librosa.org/doc/0.11.0/generated/librosa.frames_to_time.html)
support that convention. The rhythm stdlib clock instead records5ms frames and
a2.5ms midpoint. Its latency status is explicitly uncalibrated. Neither2.5ms
nor128ms explains the roughly one-second starts below. Actual resampler/physical
detector latency was not measured here; matching sample counts alone cannot
prove waveform alignment.

| Case | Truth first / second span, seconds | Inferred period / origin, seconds | Best saved A pair mean IoU |
| --- | --- | --- | ---: |
| 419 palm | [1.025750,2.648750] / [4.237167,5.860167] | .318015 / .075441 | 0 |
| 419 legato | Same419 spans | .319702 / .043614 | .600350 |
| 523 palm | [.884000,2.571208] / [4.239958,5.927167] | .382500 / .277738 | 0 |
| 523 legato | Same523 spans | .382500 / .277738 | .453412 |

The419 legato chosen eight-pulse pair is **[.043614,2.601231] /
[3.240635,5.798252]**. Its starts are-.982136/-.996531s before generator spans;
ends are-.047519/-.061915s early. Both control/order arms keep this same pair:
common N=1pair/4endpoints, unchanged MAE.522025s. This is a broad window covering
pre-phrase material, not a global time-axis translation. The523 legato best A
pair is two pulses: **[1.042738,1.807738] / [4.485238,5.250238]**—a short aligned
subsection, not the whole generated phrase.

The419 palm highest-similarity A pair is **[2.937574,3.573603] /
[6.117721,6.753750]**; both lie after generated guitar phrases. The523 palm
highest pair is **[6.015238,6.780238] / [6.780238,7.545238]**, also after guitar.
Every saved palm A pair has mean reference overlap zero. Source-known construction
makes these nuisance/rest-side matches for this generated bank; it does not
establish a classifier for a real fan or a musician's rests.

## Separating geometry from algorithm selection

As a **truth-only geometric oracle**, enumerate all valid nonoverlapping windows
on the observed grid at fixed lengths2/4/8/16, without reading feature values or
performing inference. This checks what the coordinate/window constraints permit;
it does not create predictions or claim an achievable audio score.

| Case | Best grid-only mean pair IoU | One geometric four-pulse pair |
| --- | ---: | --- |
| 419 palm | .783770 | [1.029485,2.301544] / [4.527647,5.799706] |
| 419 legato | .787929 | [1.322423,2.601231] / [4.519444,5.798252] |
| 523 palm | .858661 | [1.042738,2.572738] / [4.485238,6.015238] |
| 523 legato | .858661 | Same523 geometric pair |

All four ceilings exceed.75, while actual A does not. Thus coarse grid/length
constraints reduce localization freedom but do not by themselves make strict
matches impossible. True duration/repeat lag in inferred pulses are5.104/10.098
for419 palm,5.077/10.045 for419 legato,4.411/8.774 for both523 cases. These are
not supplied musical meter or motif lengths for inference.

Confirmed source limitations: whole-window flattened cosine; one maximum-scoring
partner per anchor/length; global similarity-first ranking; cross-length dedup
within two pulses using only starts; and pulse-bin median features. Recurrence
boundaries do not use the separately computed novelty segments. A high-scoring
short or broad match can suppress another duration, and an anchor's real repeat
can lose to a higher-scoring nuisance partner. Raw pre-argmax/pre-dedup scores
were not saved, so **which pruning stage removed a better pair is unknown**.

Hypotheses requiring new controlled tests: transient guitar evidence diluted by
median pooling; the256ms spectral footprint obscuring fast palm mutes; and
unrelated click/noise similarity dominating the mixture metric. The generated
palm supports are40ms, below half a318–382ms bin, but a centered256ms FFT spreads
their feature footprint. Raw duty cycle therefore does **not** prove that the
median erased the acoustic evidence. No new feature experiment was run to
resolve these hypotheses.

Conclusion: no demonstrated timestamp conversion bug in saved coordinates;
documented algorithm/representation shortcomings against generated extents,
with physical latency and specific pruning/feature mechanisms still unknown.
Do not “fix” this by adding an offset learned from reference labels. A localizer
can improve support inside the broad legato windows but cannot recover palm
phrases absent from the proposal universe. The separate
[localization plan](../spec/PHRASE_LOCALIZATION_LANE.md) splits those two problems.

## Reverified exact case identities

The following saved-byte hashes were rechecked for these coordinates/clock
observations. Hashing source bytes is not waveform decoding. Relative paths come
from the frozen bank index and run.cases receipts; discovery ordinal maps to
`discovery/case-NN/{result.json,analysis.json,features.npz}`. No files changed.

```json
[
  {
    "case": "seed419-palm-recurrence",
    "discovery_ordinal": 4,
    "source": "6eb00f5da0095749ab919d5917d7c632763b9622ccefb97582e94ede3985866c",
    "cache": "0e79d846d4583f420d4538635cb7ef3119a387b6e3874d82e79c999b3bbec92d",
    "truth": "b2a66219ad45c62ec14f3f0049344874d9654127d2ef6968cfe0fd860009bbd6",
    "prediction": "4fa9c091f41671bdd3f27a7048ff2de1b370af77c5c05caf02f0d87a28c5b2c2",
    "analysis": "cc3b281931894afe6413a5a69b19c515ba89a1422f79408f7b7c24c969783a40"
  },
  {
    "case": "seed419-legato-recurrence",
    "discovery_ordinal": 5,
    "source": "9fa9b92c195a61e9be45846e6149590d4c7f7b8ba5ebc17675fdaee521d4782f",
    "cache": "469cb272bea3bbfc7c68096d607c845bfd952fd479d9b158d408d6ed3c9b6efd",
    "truth": "d2b823b162bc0ee388d78cc2f225f0d54957fa511203e84e0aaa962fdb153ffa",
    "prediction": "f3a9e4e5fd71b9ef54864f48e256bf4deb2d6526e87889d2b9dd637d530bb020",
    "analysis": "8978fe6f6e15854f1c78b2f9c88174b89c7acf156b369dfec2f1cbcc31d8642e"
  },
  {
    "case": "seed523-palm-recurrence",
    "discovery_ordinal": 9,
    "source": "09032a86678305fd89414b2efaf350960cbc76c33e8cd2474a27c0fcb701393d",
    "cache": "62a27a4d1afce3cdcb22366ca7962a4ba21d1884fc335bcb93f208582fbba2fe",
    "truth": "067012f03f9e3d0fef7c66db52e294de3916d41de971db787c68497cd0522514",
    "prediction": "81ccb6cefa8e496c9a546c55ce8069cb76d8622cd3e531c8d8e439c3d3fa8c7c",
    "analysis": "2ce5caa4a1e3d2df10c7de6a761d6b4bbd9b49555b574f9cd9efba51752e9624"
  },
  {
    "case": "seed523-legato-recurrence",
    "discovery_ordinal": 10,
    "source": "f5d16373afe6b3e7424dd61efd4122f9ef313c5a9426a1780a3220a26720eadd",
    "cache": "800911c95eddbe69786c25a1a05d93ac7eb250f6dd5513000570c53590454767",
    "truth": "014074f0570ce638e87c6cc2f1de50e1f81df9bd7ed33f609d06cded26578285",
    "prediction": "0f070ec23b0d5fcee8b30817bdd5ab734085b9f6b55e6c2f3d0ad0ee6dae7050",
    "analysis": "e69d8904c970a23302b993bee6db05c597f07fbec9586d698856aa332297de96"
  }
]
```

## Bounded localization geometry, not a prediction

For the proposed L1 only, existing Border intervals plus256ms context on each
side have oracle support ceilings0 for both palm cases,1.0 for419 legato and
.724871318 for523 legato. The latter cannot reach strict .75 for the full generated
phrase even with perfect trimming inside these ROIs. This post hoc geometry
check reads coordinates/labels only; no feature similarity was recomputed. It
limits the expected scope of L1 and does not authorize enlarging the margin from
consumed labels. L2 must address missing/submotif proposal support separately.
