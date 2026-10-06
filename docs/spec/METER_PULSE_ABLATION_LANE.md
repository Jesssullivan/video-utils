# Read-only pulse and meter evidence ablation

Owner: `/root/meter_inference`; admitted by root under the user's ten-hour
parallel goal, October 5, 2026. Authority: repository AGENTS.md and R-N13.
Published `scripts/meter.py` is frozen. This lane owns this plan, a dated
reproducibility receipt and isolated `artifacts/experiments/meter-pulse` outputs.

## Fixed experiment

Use six existing generated cases from the frozen root-calibration pilot:
low32 sustain, palm-muted recurrence, legato recurrence, missing fundamental,
timing reference and timing variation. Total source duration is 56 seconds.
Read already-generated MFCC0 and onset-event evidence only; no audio decode,
model inference, package installation or label-conditioned settings. Also read
the existing stronger real run `20261005T232741Z-2b5dc43fd009` as a separate
observational audit, without measured or intended meter truth.

For each opaque case, retain fitted pulse ×0.5/1/2 and compare frozen cyclic
accent ranking on (A) existing MFCC0 aggregate, (B) spectral-flux event density,
(C) SuperFlux event density and (D) spectral-flux density excluding events within
25 ms of the fitted periodic grid. D is an uncertainty ablation, never recovered
guitar: it can remove guitar attacks and leave half-time off-grid clicks. Freeze
all ranking thresholds and period candidates from the published meter worker.
Do not select the best alias using generator BPM, intended meter or IoU labels.

Report alias-specific pulse counts, strongest cycle, heuristic explained
variance, holdout similarity, abstention, rejected-event fraction and evidence
coverage. Compare residuals to subdivisions 1/2/3/4/5/7/8 as descriptive evidence;
denser subdivisions inherently reduce residuals and cannot win a BPM decision
by residual alone. Save every prediction before opening generator truth for
evaluation. If meter/downbeat annotations are absent, no meter accuracy is
calculable; report that absence rather than treating a rendering BPM as meter.

## Primary basis and proposal boundary

[FMP local pulse](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C6/C6S3_PredominantLocalPulse.html)
describes measurable pulse levels and octave switches; pulse is not unique
metrical notation. [Krebs, Böck and Widmer](https://www.cp.jku.at/research/papers/Krebs_etal_ISMIR_2013.pdf)
learn metrical patterns jointly with tempo/downbeats and use separate frequency
bands; their constant 3/4 and 4/4 ballroom evaluation does not validate technical
deathcore or odd tuplets. [dPLP](https://www.audiolabs-erlangen.de/resources/MIR/2025_ChiuSM_dPLP_ISMIR)
is a current author-published differentiable pulse research direction. We do
not download its models or claim learned metrical inference here.

Definition of done: hash-verified source/code inputs before and after, six
label-free predictions followed by explicit evaluation limits, real-run
observational comparison, and a concrete next-lane proposal. Two numerical
threads maximum (this pass uses stdlib), no canonical registry/analysis/latest
writes. At most 60 seconds unique generated audio is inspected through cached
features; no decoding. Stop at 120 seconds elapsed using a parent timeout.
Coordinate phrase-window owner so half-time pulse does not silently force a
minimum four-pulse musical phrase length. Existing unknown meter is a valid
abstention, not a label to replace with 4/4.
