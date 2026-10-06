# Bounded phrase-support localization and later proposal recovery

State: root authorized **diagnostic research and this plan only**. No canonical
worker, frozen harness, default, generated bank or actual take changes. Root must
admit exact future source/settings, source tests and numerical stages separately.
Authority: operator project goal, AGENTS.md, R-HOOK-CONVERGENCE-20261004/R-N13.

Automatic phrase/riff discovery remains score-free. Musical intent, confirmed
tonic/mode, tuning-derived played notes, meter and a predefined arrangement are
not prerequisites. Output is an acoustic support/recurrence hypothesis for
navigation; it never grades a missed/extra note or a musical mistake.

## Evidence and post hoc rationale

[Consumed-case diagnostics](../agent-notes/2026-10-06-phrase-localization-diagnostic.md)
show consistent source/frame/grid arithmetic, nonempty bins, one broad419 legato
match with approximately1s early starts, short523 legato subsequences and no
overlapping palm proposal. The order filter reduces false candidates but does
not move endpoints. Truth-only geometric ceilings exceedIoU.75 in all four
positive cases, so grid constraints alone do not explain strict failure.

This rationale was chosen **after examining consumed419/523 failures**. Those
cases are development/error-analysis data from this point onward. The diagnostic
does not prove which feature/pruning mechanism failed or independently calibrate
FFmpeg/onset latency. New label-bound offsets and adaptive thresholds learned
from those spans must never enter discovery.

Primary research supplies a direction, not deathcore accuracy evidence:

- [Müller/Jiang/Grosche audio thumbnailing](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C4/C4S3_AudioThumbnailing.html)
  treats recurrence as paths inducing variable segment support and uses both
  explanation quality and coverage. Our bounded localizer borrows path support,
  not their full-song exhaustive optimization or their example's parameter values.
- [AudioLabs path enhancement](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C4/C4S2_SSM-PathEnhancement.html)
  connects diagonal paths with repeated intervals and discusses different slopes
  for tempo variation. Longer diagonal smoothing can erase changing-rate paths.
- [Foote novelty procedure](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C4/C4S4_NoveltySegmentation.html)
  identifies changes between contrasting acoustic regions. A texture transition
  is supporting context, not automatically a musical phrase boundary.
- [librosa STFT](https://librosa.org/doc/0.11.0/generated/librosa.stft.html)
  describes the time/frequency tradeoff and centered-frame convention. Keep the
  32Hz-capable long-window branch; any future short attack branch must be a
  separate view with no low-note transcription or master high-pass claim.

## Minimal reversible implementation proposal: L1

Implement a NEW isolated cache-only `phrase-support-localize` worker and source
tests after review. Input: exact hash-bound frame features/times and original
`Border` proposal receipts. Freeze frontend, original candidate universe,
ranking/order filter and cap10. Control retains the original windows; treatment
keeps the same candidate IDs and exposes separate localized support. Never
quietly change original endpoints, scores or upstream receipts.

For each candidate, inspect only its two existing intervals with at most256ms
extra context on each side, clipped to the recording. Inside these bounded
rectangles, select a contiguous, temporally ordered off-diagonal support path.
Start with fixed-rate diagonal support as the smallest controlled change;
bounded rate adaptation is a **separate later arm**, not an implicit fallback.
Do not use generated phrase spans, note events, supplied BPM or future truth.

Proposed engineering constants to freeze before implementation/generation:
retain existing dimension scaling and frame-cosine .8 match threshold; minimum
support duration.5s; maximum unsupported consecutive run128ms; preserve existing
competitor/order margin.10. Compute endpoint support from path projections at
the16ms frame clock, not pulse edges. Missing/nonunique ordered support returns
`localization_unknown` with the original candidate and a reason. Do not snap
independent endpoints to arbitrary loud novelty maxima—the prior C arm exposed
that risk. The following exact first-arm rules are a review proposal, not
admitted working settings. Standardize fine cached frames with the same
active-dimension/std>1e-5 and clip[-4,4] rule applied to the fine frame sequence;
this bundles finer pooling with localization and cannot isolate their individual
effects. Build only the candidate's two-ROI cross-similarity tile. Zero-norm cells
have no match. Fixed diagonal local accumulation uses
`D[i,j]=max(0,D[i-1,j-1]+cosine[i,j]-.8)`, with no horizontal/vertical warp steps.
Reset after more than128ms consecutive nonpositive rewards; start/end on positive
reward cells. Require at least.5s support on both axes. Select the highest total
reward valid path; equal scores within1e-12 with different extents abstain rather
than choosing convenient boundaries. No reference controls path starts/stops.

Proposed stationary-texture guard: each projected path must contain at least
two internal adjacent-frame changes whose dimension-normalized RMS z difference
is≥.25, separated by≥128ms and excluding128ms at both outer endpoints. If active
dimensions are empty or this test fails, retain the raw candidate with
`stationary_or_insufficient_internal_change`; expose no localized phrase claim.
This is an acoustic variability heuristic, not a guitar classifier: noisy fan
textures can pass and legitimate single-tone guitar can abstain. Freeze it before
new labels and test those failure classes. Existing competitor/order eligibility
is not recomputed or retuned, and original cap/ranking remains unchanged.

Novelty or saved spectral/SuperFlux attack context may annotate localized edges,
but should not gate L1 discovery. An attack can be click-shaped or absent in
legato/tapping; it never certifies an intended note. A homogeneous sustain or
ambiguous repeated noise may have a path but insufficient distinctiveness:
record an acoustic texture span or abstention, not a confident musical phrase.
No probability confidence or recovered guitar stem is implied.

The256ms ROI margin has an explicit post hoc geometric limitation: the419 legato
raw candidates can cover its whole reference, while the523 legato order-candidate
ROI support ceiling is only.724871 mean pair IoU even with oracle-perfect trimming.
Both palm cases have no candidate and a zero ceiling. L1 therefore cannot produce
strict full-phrase matches in those latter cases; do not enlarge the margin using
their labels. Recovery/merging of missing support belongs to L2 and fresh tests.

Receipt contract: raw candidate ID/endpoints, ROI, path first/last frame centers,
frame-cell half-open edges,256ms FFT-support uncertainty, support/unsupported
duration, ambiguity/abstention reason, pre/post-selection count, source-axis hash,
feature-clock/hash, exact settings/worker hashes and nullable confidence. Distinguish
center timestamps, half-hop cell edges and FFT support; do not add a second
half-window offset to centered frames. Future video callouts can show raw and
localized uncertainty ranges separately; no larger flag render is released here.

## L2 proposal recovery is a separate admission

L1 cannot find palm recurrences missing from A. A later independent experiment
should replace fixed pulse-window proposals with bounded seconds-domain diagonal
recurrence support and several partner hypotheses, carrying explicit rejected
argmax/dedup alternatives. Use original frame clocks so an uncertain click-derived
pulse is context rather than a mandatory musical phrase length. Separate fine
texture/support and attack views; compare their contribution in distinct arms.

Avoid a whole150-second NxN matrix. Initial scope is bounded eight-second cache
regions with at most512 frames, processed in tiles≤256×256 and a total2million
similarity/DP-cell budget. Cap candidate pairs60/retained10 and stop with an
explicit partial-coverage receipt when the budget cannot cover a take. No “latest”
file guessing. Real-take exploration must explicitly select hash-bound sparse
regions and cannot claim full-take completeness.

## Source tests and fresh confirmation plan

Before audio inference, independently constructed feature-array tests should
cover a motif padded with unlike context (endpoints move inward), a repeated
submotif inside a longer changing phrase (retain hierarchy/uncertainty), constant
sustain and ordered click/noise controls, adjacent rests, legato without picked
attacks, onset/texture disagreement, recording edges, ambiguous ties, invalid
span ordering and no path. Time tests include native48k→analysis16k mapping,
16ms frame centers, centered versus uncentered conversion and deliberately
missing bins (preserve an explicit time axis; never compress indices). A later
rate arm needs independent shifted/rushed/omitted-support tests with raw offsets
kept; DTW must not conceal unsupported or changed timing.

Propose fresh **seeds617/719**, each six8-second cohorts: low32 sustain,
linear missing-F0 sustain, temporally ordered click/noise-only, fan-envelope-only,
palm recurrence and legato recurrence. Twelve clips/96seconds, eight negatives
and four positives. Both seeds remain withheld from setting selection. Metadata
must freeze independent motif placement/duration, non-grid alignment, internal
rests, nonconstant nuisance envelope and click timing before waveform generation;
share nuisance components across each seed's positive/negative cases. Include a
nontrivial ordered nuisance case since the prior click-only controls produced no
candidate opportunity. Renderer/native/missing-F0/component-sum proofs follow
the existing source-bound construction protocol. This is metadata planning;
no new plan file, generator, audio, model job or inference is started here.

Only after root admission: two threads, sequential≤12cases/96seconds,
120seconds/case/600seconds overall through sealing; exact cache/worker/settings
and binary receipts, no downloads/pitch job, immutable output and owned process
group cleanup. Freeze every control/treatment prediction before truth opens.
Scoring uses the **full identical reference set** at IoU.5/.75, boundary matching
20/50/100ms, per-seed/cohort negative false candidates and explicit source-time
support coverage. Endpoint means use common reference-pair intersections with
Ns/lost/gained IDs/null outside intersections; report all-reference recall too.
An abstaining treatment remains in the denominator. Distinguish cap, threshold,
localization and no-proposal failures, with a geometry-only oracle confined to
evaluation/error analysis. No oracle boundary enters discovery.

Retain raw candidates in a separate provenance array; score actionable localized
support separately with abstentions counted as missed references. A raw fallback
must not be credited as a successful localization. Report raw-control metrics
alongside localization coverage, so an apparent precision gain cannot hide lost
navigation recall or narrower evaluated coverage.

Admission DoD: independent source oracles and integrity/resource checks pass;
saved numerical results expose strict-boundary and palm recall failures as well
as gains; negative false candidates do not regress on either seed and positive
recall does not fall. Any relative gain still needs useful absolute navigation
accuracy and separate musician review before a product default or bigger marked
video. Keep unknown timing calibration, pitch/tonic/mode/meter and musical intent
unknown. Publish failures without tuning the same confirmation labels.

## L1 source-only checkpoint

Root subsequently admitted only the NEW L1 worker and independent constructed
feature-array tests. The historical engineering plan admitted for that stage
had SHA256 `230022f9a0d059036e8fadb62315b1abcd7108166df81b73ffb72a7828584273`;
the text above is preserved. The frozen worker SHA256 is
`a64ff3acc5f18931e9975e96d1c6e80a1d454272fbf9dd4925b8b835b8c509de`.
[Independent source audit](../agent-notes/2026-10-06-phrase-localization-source-audit.md)
records22 standard-library checks passing with site packages disabled, clock/
support oracles, strict metadata/resource bounds and a changing-noise guard
limitation counterexample. This is source proof only. Fresh-bank metadata,
waveform generation, numerical inference/evaluation, actual recording changes
and product-default adoption remain separately unadmitted. The ROI ceilings,
missing-palm limitation and required common-reference quality metrics still
apply unchanged.
