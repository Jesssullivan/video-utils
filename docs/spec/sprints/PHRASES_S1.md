# S1 phrase proposal research protocol

Owner `/root/s1_phrases`; sprint parent `docs/spec/sprints/20261006-S1.md`
(root checkout owns that administration file); lane TIN-5565. Authority is the
operator's six-agent five-hour sprint request and R-HOOK-CONVERGENCE-20261004,
R-N11/R-N12/R-N13. Existing accepted media and all30 product tools remain intact.

The previous617/719 experiment recovered0/4 full pairs and0/16 endpoints.
Some reference regions were outside the raw proposal geometry, so downstream
localization could not repair them. This lane tests upstream source-only
segmentation with bounded explicit clocks; it does not upgrade musical grading.

## Frozen comparison

`scripts/phrase_proposal_s1.py` is an experimental research helper, absent from
the typed product catalog. It retains one frozen baseline and exactly two arms:

* **Araw:** existing hash-pinned canonical frontend, guarded short2/4/8/16-pulse
  proposal search, same-source unseeded librosa rhythm. No generator tempo or
  arrangement seeds. Missing inferred pulse abstains with full reference counts.
* **S1_support:**25–6000Hz logarithmic-band power, observed low-band activity
  above a20th-percentile floor, low-band fraction guard,0.24s gap grouping,
  shape-variation rejection and32-step sequence cosine recurrence.
* **S2_multiscale:** the same thresholds with0.12/0.24/0.40s gap grouping,
  deterministic both-span-IoU deduplication and a10-pair cap.

The activity/timbre gates are uncalibrated acoustic heuristics. They are not
guitar identity classifiers, and constant32Hz/music or click-only rejection in
generated fixtures does not establish general instrument specificity. Spectral
analysis includes approximately32Hz, uses no blanket high-pass and does not
alter the source. A4096-sample centered16kHz FFT has256ms support, so a16ms hop
does not confer16ms acoustic boundary precision. Generated phrase durations are
not forced into detected pulse lengths. Boundary shifts and raw baseline
limitations remain visible in the scores.

## Heldout generation and evidence isolation

Seeds1301 and1423 are new relative to prior617/719 runs. Each seed supplies
low32-sustain, missing-F0-sustain, ordered-click-only, fan-only, palm recurrence
and legato recurrence:12×8s clips,96s total,48000Hz mono PCM16. Palm/legato each
have one full generated identical-motif pair, including internal rests:4 pair
references and16 typed endpoints overall. The four negative cohorts have zero
generated riff references; that does not deny acoustic periodicity. This is new
random geometry and nuisance realization within the prior recipe family, not
validation on a new recording distribution or physical-technique acceptance.

Motif placement/duration and nuisance phases use separate SHA256 namespaces.
Native-sample rounding fixes geometry before audio synthesis. Fan/noise bytes
are shared across six cohorts within each seed; clicks are shared across five,
with fan-only explicitly click-free. Components and mixture are independently
PCM16 quantized; a2LSB sum error bound is checked. Missing-F0 synthesis remains
linear, and the32Hz isolated component is retained as evidence, not filtered out.

`preregister` emits only immutable metadata. Root releases the source/plan
hashes and phase before numerical work. `generate` writes components and truth;
`discover` reduces the bank to opaque source paths/hash identities and starts a
separate process per source. Source-only discovery accepts no truth, cohort,
expected notes, spans or generator BPM. It saves all12 predictions before a
global hash seal. Only `score` opens truth, after verifying every prediction and
its source binding. Settings cannot be retuned and rescored on these labels.

## Metrics, bounds and completion

PairIoU0.5/0.75 requires **both** span axes; the frozen evaluator uses maximum
cardinality, then maximum mean IoU. Typed first/second start/end endpoints are
matched one-to-one independently at20/50/100ms. Matched-pair endpoint MAE has an
explicit4×matched-pair denominator; null means no match, not a perfect result.
All references, including abstentions, stay in denominators. Negative false
candidates are reported separately for each negative cohort and seed. Aggregate
counts are sums, never averages of per-case recall. Positive partial proposals
can therefore have matched endpoints while failing full-pair IoU.

Resource declaration: at most two numeric threads; one phrase job occupies one
of the sprint's two heavy-job slots. Overall900s and120s/source; opaque child
processes use bounded `subprocess.run` and are reaped if they time out. Its only
decoder subprocess has20s timeout, one FFmpeg thread and exact8s PCM extent.
An external root wall-clock wrapper bounds the whole released run. JSON2MB,
WAV1MB/file, feature1024frames×64dimensions, at most180 multiscale segments and
10 retained treatment pairs. No model, download, installation or host daemon.

Completion requires frozen source/preregistration hashes, actual sealed
predictions/results, independent denominator/metric verification and targeted
refusal/interface tests. Non-improvement is a completed research result. No arm
becomes a default, typed product tool, detected musical mistake, note score or
real listening acceptance from this pilot. A future admission would need a
separate root decision, closed MCP schema/skill and credible broader evidence.
