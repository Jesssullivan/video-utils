# Meter/pulse cached-feature ablation receipt

Actor `/root/meter_inference`; target owned new plan/receipt/harness and isolated
`artifacts/experiments/meter-pulse`. Reason: operator's full parallel ten-hour
goal, root's bounded six-case read-only assignment. Authority: repository
AGENTS.md, R-HOOK-CONVERGENCE-20261004 and R-N13. No process signalling, host
changes, canonical worker/registry mutation, media rendering or latest-pointer
write occurred.

Plan: [METER_PULSE_ABLATION_LANE.md](../spec/METER_PULSE_ABLATION_LANE.md).
Reproducer: [dated Python harness](2026-10-05-meter-pulse-ablation.py). Run with
`python3 docs/agent-notes/2026-10-05-meter-pulse-ablation.py --output artifacts/experiments/meter-pulse/NEW_RUN`
inside a parent `subprocess.run(..., timeout=120)`. Stdlib execution; numerical
thread variables capped at two. No new tests or published processing code were
needed for this reversible experiment using the frozen, tested meter scorer.

At 2026-10-05 23:52 UTC, latest isolated receipt:
`artifacts/experiments/meter-pulse/run-20261005-02/receipt.json`, SHA256
`6220a1cc420d06ae4ed69f26a45e28da5e2460c8717f3b2dea2b0b820062cd8b`.
Six generated cases/56 seconds of existing cached features plus the stronger
real run's existing feature JSON were inspected. **No audio was decoded.** The
second run added evaluation descriptors; all six predictions and the actual
observation are byte-identical to run-01. Hash verification before/after proved
cached sources, analyses and canonical meter/DAG source unchanged during each
run. The earlier labels were already development-bank evidence in sibling
experiments; this ablation is not a held-out musical validation.

## Findings

All **72 generated-case variant/alias combinations** and all **12 real-run
combinations** abstained. No notated meter or additive partition was inferred.
For the four eight-second cases, approximately 89 BPM yields fewer than the
scorer's 12 required pulses. Its faster approximately 178 BPM alias has enough
pulses but insufficient repeatable accents. Short samples and weak accents are
different abstention causes; neither establishes the absence of musical meter.

| Existing generated cases | Fitted pulse BPM | Faster alias BPM | Four fitted pulses | Four faster pulses |
| --- | ---: | ---: | ---: | ---: |
| Sustain/palm/legato/missing-F0 | 88.994918 | 177.989835 | 2.696783 s | 1.348392 s |
| Timing reference/variation | 89.005236 | 178.010471 | 2.696471 s | 1.348235 s |

The rendering BPM is 178 for these fixtures, read **after** all predictions.
The faster observed alias is within 0.006% of that rendering parameter. This is
pulse-family agreement, not meter accuracy. Generator truth has phrase,
recurrence and pulse metadata but no time-signature or downbeat labels. Meter
accuracy and meter false-positive rates therefore remain unmeasured.

Fixed 25 ms exclusion around the fitted grid rejected **0%** of spectral-flux
events in four eight-second cases, **2.86%** in timing reference and **1.72%**
in timing variation. Those exclusions did not identify guitar events. The
nearest mixture spectral attack to each renderer click has a median signed
offset of **36.35–37.12 ms** across cases. Because attacks can overlap guitar,
this descriptor is not detector-delay calibration or proof of click identity.
It explains why masking an uncalibrated grid can be nearly inert even with
substantial click contamination; the exclusion variant is rejected as a default.

The stronger real take contains 581 spectral-flux and 495 SuperFlux candidates.
The grid exclusion rejects only **5.85%** of spectral candidates. All proxies
abstain at **177.602882**, **88.801441** and **44.400720** BPM. Spectral event
residuals shrink when the subdivision grid is made denser: at the faster alias,
median residual changes from **38.83 ms** at one subdivision to **7.52 ms** at
eight. That monotonic opportunity to approach any event is not evidence of
eighth subdivisions, septuplets, correct playing or a time signature.

## Concrete next-lane proposal

Keep canonical meter unknown and its thresholds frozen. Phrase searches must
expose duration alternatives without silently equating the fitted half-time
pulse with a quarter-note bar. Share pulse-family metadata with phrase search;
candidate duration and recurrence evidence may rank search proposals, but a
phrase cycle need not be a bar.

Before learned ranking, admit a separate calibration/annotation lane: click-only,
guitar-only and deliberately overlapping guitar/click fixtures with known
sample events; compare spectral-flux/SuperFlux timestamp conventions at native
rate. Preserve onset delay and overlap uncertainty per detector. Use low-band
and high-band onset strength separately (protect approximately 32 Hz), plus
chroma change, spectral texture and recurrence, rather than MFCC0 or attack
count alone. A hard high-frequency cut is not guitar/click separation.

A future bounded joint ranker should retain pulse level, phase, accent cycle,
subdivision and unknown hypotheses. Start with an interpretable feature ranking
over the fixed candidate family; only then consider a small learned observation
model. Train/evaluate on separately frozen, musician-annotated meter/downbeat
data spanning 3/4, 4/4, genuine odd/additive meters, seven-subdivision-over-four
counterexamples, polymetric riffs and legato. Split by motif/source before
training; measure alias errors, downbeat timing, abstention and incorrect
confident labels on held-out sources. Do not fit rendering BPM or current bank
IoU targets into discovery. An operator's declared BPM is optional context
with separate provenance, never an injected score or required arrangement.

Primary grounding remains [FMP's pulse hierarchy](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C6/C6S3_PredominantLocalPulse.html),
[the authors' joint pattern/tempo/downbeat work](https://www.cp.jku.at/research/papers/Krebs_etal_ISMIR_2013.pdf)
and [current dPLP research](https://www.audiolabs-erlangen.de/resources/MIR/2025_ChiuSM_dPLP_ISMIR).
These motivate the proposal; none establishes deathcore-specific accuracy or a
trained model shipped in this repository.
