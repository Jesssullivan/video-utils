# Isolated phrase-window causal ablation

Authority: root's operator-authorized parallel ten-hour goal and R-N13. This
lane owns this specification, a dated reproducibility receipt/harness and
isolated copies under `artifacts/experiments/phrase-window-ablation`. It does
not change canonical workers, registry, actual pilot, latest pointers or media.

## Fixed question and controls

The frozen unseeded pilot has paired recurrence TP0/FP4/FN5 at IoU0.5. Its
palm/legato pulse estimate is about89BPM, while its shortest4-pulse search window
is about2.697s. The renderer's paired motifs last about1.348s. Those values
motivate an experiment; generator duration/BPM is never supplied to discovery.

Use exact frozen bank
`artifacts/benchmarks/root-calibration-bank-20261005T2255/fixtures.json` and pilot
`artifacts/benchmarks/root-calibration-pilot-20261005T2300/phrase-pilot-index.json`.
Select palm-muted and legato recurrence, timing-reference and timing-errors,
plus sustained32Hz and missing-fundamental negative cases: six cases/56 seconds
of unique audio. Every discovery input is an opaque byte-identical alias. Truth
and semantic IDs are attached only after all variant predictions are saved.

Extract the canonical phrase frontend once per case, preserve frame-feature
cache and repeat the unchanged baseline search on that cache. Require exact
baseline recurrence equivalence to the original pilot before attributing a
change to windows. A mismatched baseline aborts the causal claim. Keep frontend,
threshold0.8, scaling, cosine scoring, nonoverlap and candidate cap fixed.

| Variant | Change | Interpretation |
| --- | --- | --- |
| baseline | Inferred pulse;4/8/16-pulse windows | Frozen control |
| short-pulse | Same pulse;2/4/8/16 windows | Isolates short-window admission |
| pulse-alternatives | Same features, inferred pulse×0.5/1/2;2/4/8/16 windows | Tests half/double ambiguity; no chosen metrical truth |
| seconds-domain |50ms aggregation;0.5/0.75/1/1.5/2/3s windows | Search independent of musical pulse notation |

All candidates remain heuristics. A positive result must include paired IoU0.5
and0.75 TP/FP/FN, candidate counts, endpoint offsets/coverage, negative-case false
positives and unknown detector/boundary confidence. More true matches accompanied
by many false positives are a tradeoff, not an automatic improvement. No musical
phrase semantics, time signature, tonic, mode or mistakes become confirmed.

## Bounds and definition of done

Root admitted this six-case experiment with numerical threads capped at2.
Decode only56seconds once; reuse exact frontend features for all search variants.
At most256 aggregation frames,60 candidates per variant/case and bounded
256×256 similarity cells per individual window. Sequential cases,120seconds
per case,600seconds lane elapsed ceiling checked between cases (not a preemptive
watchdog); no model/download, package installation,
full pilot or host configuration change. Preserve source and cache hashes.

Done means baseline identity check plus source-bound measurements for all four
variants, isolated predictions written before evaluator truth reads, and a
concrete adoption/rejection proposal with regressions visible. Initial results
are development-bank evidence; withheld variants and real-take listening remain
required before canonical change. This task alone does not authorize core edits.

Primary basis: [AudioLabs self-similarity matrices](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C4/C4S2_SSM.html)
and [librosa recurrence controls](https://librosa.org/doc/0.11.0/generated/librosa.segment.recurrence_matrix.html)
support comparative temporal feature analysis and explicit temporal exclusion.
[librosa tempo documentation](https://librosa.org/doc/0.11.0/generated/librosa.feature.tempo.html)
describes a tempo estimate rather than a metrical proof. Window scales and bounds
here are fixed engineering hypotheses, not musical-ground-truth parameters.

## Completed isolated checkpoint

The dated [receipt](../agent-notes/2026-10-05-phrase-window-ablation.md) and
[reproducibility harness](../agent-notes/2026-10-05-phrase-window-ablation.py)
record the six-case result. Baseline recurrence identity passed every case.
At paired IoU0.5, baseline TP0/FP4/FN4 becomes TP3/FP11/FN1 with only the extra
two-pulse windows. Precision0.214 and stricter IoU0.75 TP1 show unresolved
false-positive and endpoint problems. Pulse unions and seconds search add no
true pairs while increasing false candidates substantially; they are rejected
as defaults at this checkpoint. The proposal is a guarded short-window option
plus boundary/discrimination experiments, conditional on later root ownership
assignment and held-out validation. Canonical source is untouched.

## Second ablation proposal: fixed controls and held-out variants

Root has released isolated A/B/C/D implementation and development-cache checks.
Canonical adoption remains outside this lane. Both held-out seeds remain withheld
until root releases generation and inference after the formula/source freeze.

The first experiment's labels have already been inspected, so that bank remains
development evidence. Generate a new held-out bank using fixed seeds **211 and
307**, six ten-second clips per seed: palm-muted recurrence, legato recurrence,
timing-reference, timing-variation, continuous low32 sustain and missing-F0
sustain. Total12 clips/120 seconds; two negatives per seed. Both seeds are
held out from subsequent knob selection. The original fixed bank is the only
development set, not part of the held-out score. Save generator/configuration
hashes and freeze variant settings before any held-out label evaluation.

For each seed, vary phrase placement and gaps, observed spectral/noise color,
click/pick overlap, low-string32Hz harmonics and upper notes within the fixed
instrument context. Positive motifs use lengths drawn before generation from
0.8–2.0seconds, independent repetition placement and legitimate rests/tuplets;
timing variation includes separately labeled renderer shifts/omissions. Negatives
have no declared recurrence: sustain or missing fundamental with changing fan-like
noise, stationary pitch, click rates that vary independently of the musical
texture, and click-shaped guitar transients. Do not make silence/absence of clicks
the only way to recognize a negative. Generated labels remain evaluator-only.

Fixed label-free variants share the same frozen frontend and2/4/8/16-pulse search:

| Arm | Fixed change | Intended causal test |
| --- | --- | --- |
| A | Short-window control; existing0.8 cosine threshold;60-candidate cap | Reproduce development gain and held-out regressions |
| B | Require match cosine minus median same-length nonoverlapping competitor cosine ≥0.10; retain at most10 pairs, ranked by that contrast | Distinguish a repeated motif from widely homogeneous sustain; contrast is not correctness confidence |
| C | Preserve A's candidates; refine endpoints independently within one inferred pulse, capped0.75s, using a fixed200ms frame-feature novelty context | Test acoustic endpoint evidence separately from candidate suppression |
| D | Apply B and C together without additional thresholds | Measure interaction; do not credit refinement with a ranking-only gain |

The0.10 contrast,10-pair cap and200ms context are preregistered engineering
hypotheses, not fitted labels or universal guitar thresholds. Keep all rejected
candidate counts/reasons and raw/refined endpoints. A bounded onset alone does
not establish a phrase boundary or a picked note; legato/sweep ambiguity remains.
If candidate endpoints have no clear novelty anchor, retain the original endpoints
and mark refinement abstained. Refinement must preserve positive ordered,
nonoverlapping source spans; do not optimize endpoints against reference IoU.

Evaluate every arm once using one-to-one paired IoU0.5/0.75, signed endpoint
errors and coverage, TP/FP/FN by seed and case, contrast distributions and
abstention counts. Report negative false candidates separately from positive
precision. Preserve pre-ranking counts so a cap cannot masquerade as better
acoustic discrimination. Unknown/all-empty denominators remain explicit.

Definition of done is reproducible, frozen label-free predictions for all12
clips and complete post-discovery measurements; poor scores stay visible. A
future **guarded option** is eligible for a root proposal only when held-out
recall is at least the A control, negative false candidates decrease on both
seeds, and the endpoint arm improves matched endpoint error without reducing
paired IoU0.75 true matches. These relative criteria prevent claiming a win from
one favorable aggregate; they are development decision gates, not real-player
or listening acceptance. If an arm fails, retain the result and freeze it rather
than retune the same held-out labels. Another threshold revision requires a new
explicitly admitted, separately held-out generation seed.

Resource proposal: two numerical threads, sequential cases,120seconds unique
audio decoded once, caches reused across four arms, at most256 aggregation
frames and65,536 similarity cells per window,60 proposals before ranking,
120seconds per-case elapsed check and600seconds total elapsed ceiling. No models,
downloads, full pitch pilot, real-take writes or canonical registry/worker changes.
The executor must use a bounded preemptive per-case timeout before any production
tool adoption; the first isolated harness's between-case checks do not prove one.

## Exact frozen A/B/C/D implementation

The dated [cache-only harness](../agent-notes/2026-10-05-phrase-guarded-arms.py)
is frozen at SHA256
`78ca89de9cea327cc4ec1096a83522781a08bc161819699b69797ca273e2fb6c`;
settings SHA256
`f50e31ee6eba0966580f78c9124938b4cdf116a6242eed2b0e7b2bb147f32edd`.
Its canonical source dependency remains
`2ed031e8000cbcda92b504db10c98de03f456c90573cbff815cbb940c9ac86fe`.
The canonical source is read/verified, not edited. The short search is the exact
frozen recurrence function with only4/8/16 replaced by2/4/8/16.

**A:** Aggregate canonical frame features by median into inferred pulse bins,
starting at the source-bound automatic pulse origin. Scale each active feature
dimension by its global standard deviation, drop dimensions with standard
deviation≤1e−5, and clip standardized values to[−4,4], exactly as the frozen
search does. Windows use2/4/8/16bins and the original0.8cosine/nonoverlap/
deduplication/60-proposal rules. No BPM or score from a generator is supplied.

**B:** For candidate windows starting at integer pulse-bin indices `i,j` with
length `L`, flatten the same standardized windows and normalize by their L2 norm.
For each anchor separately, collect competitor window starts `k` satisfying
`abs(k-anchor) >= L`, `k != chosen_partner`, and window norm≥1e−6. The exclusion
is relative to that anchor; a competitor may overlap the chosen partner. Exclude
only the exact chosen partner start, rather than selectively removing similar
neighbors. Take each anchor's median competitor cosine; the baseline is the
arithmetic mean of those two medians. Missing either competitor set abstains.
Contrast is `cos(i,j) - baseline`. Keep contrast≥0.10, with a1e−12 arithmetic
comparison margin, and rank by descending contrast, descending match cosine,
earlier first start, earlier second start, shorter pulse length, then stable
original index. Keep at most10. Preserve every competitor count/median, rejected
proposal reason and cap exclusion. This is heuristic distinctiveness evidence.

**C:** Standardize native frame features using the same active-dimension rule.
At frame time `t`, novelty is RMS across feature dimensions of the difference
between the mean feature vectors in `[t−0.1,t)` and `[t,t+0.1)`. Require complete
200ms context inside available source frames. Global threshold is
`max(0.25,75th_percentile(novelty),median(novelty)+0.5*MAD(novelty))` over valid
frames. This is the existing style of engineering novelty threshold, not a
reference-fitted setting. A qualifying peak satisfies score≥threshold,
score≥left neighbor and score>right neighbor.

For each of the four raw candidate endpoints, search peaks within
`min(inferred_pulse_period,0.75)` seconds, independently. Select the highest
novelty score; ties choose the peak nearest the raw endpoint, then the earlier
source time. If no qualifying peak exists, retain the raw endpoint and abstain.
Recording endpoints0/duration remain fixed. If the four independently proposed
endpoints fail `0 <= first_start < first_end <= second_start < second_end <=
duration`, revert all four, recording the failed refinement. Never delete an A
candidate because refinement failed. Rebase detected onsets to the resulting
half-open spans, while preserving raw endpoints and original search pulse count.
Refinement confidence stays null; it does not establish a semantic phrase.

**D:** Apply the identical C transform to the identical B selection. No separate
threshold, ranking or truth-dependent endpoint choice exists. Thus C has A's
candidate count and D has B's count, even when refinement abstains.

The input cache index contains at most12 rows/120seconds: `id`, relative `cache`
NPZ path, `cache_sha256`, `source_sha256`, `duration_seconds`,
`inferred_pulse_period_seconds` and `observed_pulse_origin_seconds`. Caches contain
only `features` (feature×frame), `times`, `centroid` and `onsets`; no reference
boundary/score/warp field is read. NPZ expansion is checked before allocation:
exactly four members and at most1MB uncompressed. Native frames≤1000,
aggregation frames≤256, finite/ordered source times,12second individual duration
and two numerical threads remain bounded. Stable cache/index hashes are verified
after computation. The cache-only harness performs no waveform decode, network,
model or subprocess operation.

Structural self-tests and development-cache results are recorded in the dated
freeze receipt. Development A reproduced the prior short-window output. B
removed five missing-F0 false proposals with the fixed contrast rule; C/D reduced
IoU0.75 true pairs from one to zero. That regression is retained without retuning.
Both held-out seeds remain available for a single frozen-formula evaluation; these
development results do not satisfy the held-out decision gates above.

## Completed held-out checkpoint and next metadata-only proposal

Root released the structurally verified12-case120second bank after the source
freeze. The [held-out receipt](../agent-notes/2026-10-06-phrase-heldout-results.md)
and [isolated runner](../agent-notes/2026-10-06-phrase-heldout-runner.py) retain
sources, all predictions before truth reads, exact settings, per-seed scores,
filter/cap reasons and identical-reference endpoint audits. Execution completed
in91.733seconds; no formula or threshold was retuned.

At paired IoU0.5, A is TP2/FP125/FN6; B TP2/FP89/FN6; C TP4/FP123/FN4;
D TP4/FP87/FN4. All arms have **zero true matches at IoU0.75**. Negative
candidates drop49→24, including23 contrast exclusions and two cap exclusions.
Common-reference endpoint comparison exists for only one A-versus-C/D pair:
four endpoints0.562s→0.338s; the other control pair is lost. This does not support
default adoption. Both211/307 are consumed for confirmation and may not be
reclassified as untouched data after settings changes.

The next proposal is **metadata only**, with no audio generation, inference,
code change or adoption authorized by this section. Root must assign an owner,
admit exact parameters and release stages separately. The failure being tested
is cosine self-similarity on homogeneous musical sustains or click-driven
textures masquerading as a temporally distinct motif.

Propose fresh seeds **419 and523**, five eight-second cohorts per seed: sustained
low32Hz guitar plus independently timed clicks/noise; missing-F0 sustain plus
the same nuisance design; click/noise-only; repeating palm-muted motif; repeating
legato motif. Total10 clips/80seconds, with six negative and four positive cases.
Keep32Hz harmonic content, click-shaped guitar transients, legitimate rests and
nonconstant noise envelopes. Match nuisance parameters across appropriate
positive/negative constructions so silence or click absence is not a shortcut.
Freeze placement/duration/gain/noise/click recipes before generation; no reuse of
211/307 labels for knob selection. Fresh generator seed metadata is not a BPM or
reference supplied to inference.

Compare only two fixed arms on the identical frozen A proposal universe and
identical10-pair cap: existing B contrast/ranking as control, versus B plus a
temporal-order distinctiveness diagnostic. For each lengthL candidate, keep its
first feature window fixed and cyclically rotate only the second window by
each offset1…L−1. Use the median rotated cosine as an order-null baseline;
require true cosine minus that baseline≥0.10, independently of the original
competitor contrast. Do not rotate both windows identically, which preserves
their dot product and is not an order-null experiment. Preserve all exclusions
and pre/post-cap counts. The0.10 margin is a new preregistered engineering
hypothesis, not fitted against consumed labels; order-poor palm mutes may abstain.
Click-only rhythmic patterns can also have genuine temporal order, so this
diagnostic alone cannot prove a guitar motif or remove metronome confounding.

Evaluate the full identical reference universe per case/seed, with matched and
unmatched pair IDs. Primary TP/FP/FN remains paired IoU0.5 and0.75. Compare
endpoint errors only on explicitly identical reference-pair intersections, with
common-reference Ns, lost/gained pair counts and null errors outside that
intersection; report all-reference recall separately. Keep a fixed cap in both
arms so truncation is not credited as acoustic discrimination. Report false
candidates separately for sustain, missing-F0 and click-only negatives, and
detectable-attack confidence remains unknown rather than silently qualifying.

The experiment's definition of done is frozen predictions and honest measured
results, including zero quality or a negative result. A research gain requires
lower negative false candidates on both new seeds without lower positive recall;
those relative criteria still do not constitute useful absolute phrase accuracy
or musician acceptance. If it fails, retain it without tuning the same held-out
labels. Preserve the observed A/B/C/D outputs and original sources regardless.
Proposed bounds are two threads, sequential10cases/80seconds, cached frontend
reuse, maximum256 aggregation frames,60 initial proposals and10 retained pairs,
no model/pitch jobs, and the existing preemptive case/run deadlines. This section
does not start that experiment.

## Order-null implementation checkpoint, October6

Root separately admitted implementation and source tests for the fresh419/523
proposal. The [new isolated generator/runner](../agent-notes/2026-10-06-phrase-order-null.py)
and [closed settings](../agent-notes/2026-10-06-phrase-order-null-settings.json)
implement the fixed construction and equal-cap comparison. The
[preregistration receipt](../agent-notes/2026-10-06-phrase-order-null-prereg.md)
records exact source/settings/metadata-plan hashes, formulas, ten passing
source tests, primitive/label separation, time/memory limits and retained-failure
semantics. Numerical generation/inference remain held until root releases their
exact frozen inputs. No canonical default or consumed211/307 result was changed.

## Order-null numerical checkpoint, October6

Root subsequently admitted exact-bank generation and numerical execution.
[Results](../agent-notes/2026-10-06-phrase-order-null-results.md) preserve the
single244-second run: primary pair recall1/4 unchanged, false candidates51→16,
negative-case false candidates31→8, and strict-IoU.75 true positives zero in both
arms. No cap exclusion occurred, so filtering and truncation are separated. The
one common reference pair/four endpoints has unchanged .522-second mean error;
other common-reference errors remain null. The relative research criterion
passes while absolute accuracy stays poor. No canonical adoption or transfer to
the real recording is supported. Both419/523 are now consumed confirmation data.
