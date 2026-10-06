# Phrase-window causal ablation receipt

Actor: `/root/phrase_dag`. Authority: root's operator-approved parallel ten-hour
goal, explicit six-case admission, R-HOOK-CONVERGENCE-20261004 and R-N13.
Checkpoint: 2026-10-05 23:36 UTC. Owned experiment only; no canonical worker,
registry, full pilot, actual take or latest pointer was changed.

## Exact reproducible evidence

The dated companion `2026-10-05-phrase-window-ablation.py` is the durable
harness. Isolated output:
`artifacts/experiments/phrase-window-ablation/run-20261005-03/`.

| Identity | SHA256 |
| --- | --- |
| Frozen bank index | `3a6d117a50b32ad4f9e1b60921ee1b8a1d4376cc821ebcb31f14f4b8d80fdc73` |
| Frozen phrase pilot index | `38d79d8e744ad8a4e43699a1da810d42d291b616c25afb70ba7a94522b0121bf` |
| Canonical phrase worker | `2ed031e8000cbcda92b504db10c98de03f456c90573cbff815cbb940c9ac86fe` |
| Harness and saved source snapshot | `91aa63e3cae2609d8bf799aa325272f14d07a7ef26fcae1ee43419813b82d70a` |
| Results | `a333318b8e88e39b54266e01a7176e832036df389d25658200e80ef0bcbead57` |
| Post-discovery endpoint evaluation | `6435904fe1a96910115d1a8bfbaf7f9e1db4ba7f65bf009349c0d4bfa5f9780b` |
| Identity re-verification | `fe7c5f8b45f10d586b8d5ad709bd5a8b5bb3397d0b14a55a0e31e773af7b0d81` |

Six cases/56 seconds unique audio: low32 sustain, palm-muted recurrence, legato
recurrence, C1 missing fundamental, timing reference and timing errors. Numerical
libraries and FFmpeg were capped at two threads. Canonical frame features were
extracted once for each case and reused for every variant; no model download,
heavy build or full pilot was run. Final completed phase took 5.275 seconds,
excluding the earlier extraction of the cached eight-second sustain case.

The unchanged recurrence control matches the frozen pilot exactly, including
similarity, endpoints and onsets. Only inherited source-axis copies are omitted
from that identity comparison: those fields are added after the search, not
inputs to it. The copied worker's frontend is unchanged except for saving its
frame-feature cache. Each source mixture, truth, prediction and cache was hashed
again afterward; fixed indices and canonical worker remain unchanged.

Discovery receives opaque byte-identical inputs and same-source inferred pulse
metadata from the **unseeded** pilot. No generator BPM, notes, phrase lengths,
boundaries or warps enter the worker. The selected case identities route the
experiment; they are not inputs to feature/scoring functions. All predictions
were durably saved before the harness opened reference truth. This is functional
input separation, not an adversarial filesystem sandbox.

## Causal result and regressions

The selected subset contains four declared recurrence pairs. The full twelve-case
pilot has five; this six-case result does not replace the complete-bank score.
All rows retain the same frontend, cosine threshold 0.8, scaling/nonoverlap and
candidate cap. Pulse alternatives pool the inferred period times 0.5/1/2.
Seconds search uses 50 ms aggregation and fixed 0.5/0.75/1/1.5/2/3-second windows.

| Variant | TP / FP / FN at paired IoU0.5 | Precision | Recall | F1 | TP / FP / FN at IoU0.75 |
| --- | --- | --- | --- | --- | --- |
| Baseline 4/8/16 pulses | 0 / 4 / 4 | 0 | 0 | 0 | 0 / 4 / 4 |
| Same pulse, 2/4/8/16 windows | **3 / 11 / 1** | 0.214 | 0.750 | 0.333 | 1 / 13 / 3 |
| Half/double pulse union | 3 / 63 / 1 | 0.045 | 0.750 | 0.086 | 1 / 65 / 3 |
| Seconds-domain windows | 3 / 357 / 1 | 0.008 | 0.750 | 0.016 | 1 / 359 / 3 |

The two-pulse-only admission finds the palm, legato and timing-reference pairs.
It does not find timing-errors. This directly supports short-window exclusion
as one cause of the original misses under this frozen feature/score configuration.
It does not establish that correct musical phrases are now identified generally.

| Case | Baseline TP/FP/FN | Short-window TP/FP/FN |
| --- | --- | --- |
| Low32 sustain, negative | 0 / 1 / 0 | 0 / 2 / 0 |
| Palm-muted recurrence | 0 / 0 / 1 | 1 / 0 / 0 |
| Legato recurrence | 0 / 0 / 1 | 1 / 1 / 0 |
| Missing fundamental, negative | 0 / 1 / 0 | 0 / 5 / 0 |
| Timing reference | 0 / 2 / 1 | 1 / 2 / 0 |
| Timing errors | 0 / 0 / 1 | 0 / 1 / 1 |

Negative-case false positives rise from two to seven. The naive pulse union adds
no true pair beyond the short-only experiment, while negatives rise to29 false
candidates. Seconds search saturates its60-candidate cap in every case; the two
negatives alone contribute120 false positives. More search coverage is not a
usable default without discrimination and ranking.

Endpoint accuracy remains poor for two matches. Palm mean paired IoU is0.597;
its endpoints are approximately329–351ms early. Legato mean IoU is0.603;
endpoints are approximately323–346ms late. Timing-reference IoU is0.967, with
approximately14ms-early first endpoints and30ms-late second endpoints. Only that
short-window pair passes0.75. All detector/boundary confidence remains unknown;
similarity is an unvalidated heuristic. No correctness, missed-note, rushed-note,
meter, tonic or technique claims are confirmed.

## Concrete proposal

1. Admit a **guarded experimental two-pulse window option** only after root assigns
   canonical implementation files. Preserve the existing default and both search
   results for comparison until a held-out negative bank demonstrates acceptable
   false-positive behavior. This is the smallest isolated change with a measured
   gain; it has visible regressions and is not automatic quality acceptance.
2. Refine candidate endpoints using acoustic transitions at finer resolution
   than the inferred pulse before DTW/rhythm review. The observed approximately
   half-pulse boundary bias prevents two matches from passing stricter IoU.
3. Test temporal motif variation versus sustained-texture similarity and
   metronome-driven periodicity with fixed label-free gates. Preserve low32Hz
   content; sustained low notes are music, not background noise. Boundary and
   detector ambiguity should lower/abstain candidate claims, not remove truth
   denominators from evaluation.
4. Reject indiscriminate half/double union or seconds search as a default now.
   A future seconds-domain lane needs sparse distinctiveness-aware ranking,
   duration diversity and independent negative controls before admission.

Held-out generated variants and real-recording review are still needed. This
experiment used a development subset selected after the baseline failure and
cannot qualify generalization, artist technique or intended musical correctness.

## Recovery and limits

Attempt01 failed before decode because FFprobe was absent from the shell PATH.
Attempt02 extracted the sustain cache, then the comparison rejected extra
inherited source-axis fields. Both failed directories remain intact. The final
harness derives exact executable paths from frozen pilot provenance, compares
computed recurrence fields only, and reuses that hash-bound cache; the source
audio was not decoded twice. A separate postprocessing indentation failure left
`endpoint-evaluation.partial.json`; it is retained, and the complete endpoint
receipt has the distinct verified hash above.

Elapsed ceilings are checked between cases rather than by a preemptive watchdog;
the bounded fixed six-case experiment completed far below them. The copied
similarity search uses at most256 aggregation frames and256×256 cells per window.
No whole-take dense matrix was built. Source/evidence preservation and measured
case bounds are established; these receipts do not qualify a production executor.

Reproduce without cache using the same fixed bank/pilot and a fresh isolated path:

```sh
.venv/bin/python docs/agent-notes/2026-10-05-phrase-window-ablation.py \
  --output artifacts/experiments/phrase-window-ablation/NEW-RUN
```

Optional `--cache-from` refers only to a prior owned isolated extraction. Parent
owns resource admission, canonical changes, tracker evidence and publication.

Root reattached the lane and requested completion freeze plus a plan-only guarded
second ablation. The completed harness remains unchanged at the SHA above. The
specification now preregisters independent contrast/ranking and acoustic-endpoint
arms on twelve10second clips from held-out seeds211/307, with negative variation,
truth-only evaluation and relative decision gates. No held-out fixture was
generated or analyzed, no knob was adopted, and no second experiment was run.
