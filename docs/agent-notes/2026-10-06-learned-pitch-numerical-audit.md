# Independent generated learned-pitch numerical readback

Actor: `clip_baseline/mir_sources`. Authority: root's explicit saved-source/array
readback assignment, repository `AGENTS.md`, R-HOOK-CONVERGENCE-20261004 / R-N13.
Owned new files: this receipt, the adjacent independent audit `.py` and `.json`.
This lane imported NumPy 2.5.3 in the existing `.venv/bin/python`, with
`PYTHONDONTWRITEBYTECODE=1` and OMP/OPENBLAS/MKL thread settings of two. It did
not import ONNX Runtime, install/change a runtime, acquire/read a model, invoke
inference, rerun either evaluator, decode PCM, render audio, change a master or
latest pointer, or grade/listen to the operator's take.

**Result: the selected numerical readback agrees. No must-fix was found in the
frozen numerical evidence reviewed here. Poor quality and missing eligibility
remain visible; this is not real-guitar note acceptance or a default adoption.**

## Exact frozen identities

| Evidence | SHA256 |
| --- | --- |
| Learned pilot index | `e565bb13847bb7f29c64a571f17d200f12dc21853154a39400516e52657bcf5f` |
| Predictions-only freeze | `3149bf5f6bc0b716b2d969ae5f99faf53c574ccf4f36bd46a7451e9044d7551e` |
| Evaluated source, as bound by the frozen execution/evaluation receipts and prior independent source audit | `1fb883026b842857f72a70c8bf2fb757330b9ac705be36914f7a4c50cb8f7374` |
| Original evaluation JSON | `655819f1dbe5150b0de6f6e8f05cdbd11d95c6dab9f062b65c77dcd45d8790c7` |
| Bank index | `3a6d117a50b32ad4f9e1b60921ee1b8a1d4376cc821ebcb31f14f4b8d80fdc73` |
| pYIN pilot index | `5c183df75f67dfa4b6d4a7b3c13b7d79d9fcbfa0408ce90d58a80017948ed343` |
| Discovery adapter | `720a1f76103426d1cc7580d213d3516f31b184295a50d873bda545ccc5a2d40e` |
| Declared model identity, not a fresh model-file read | `2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec` |
| Runtime manifest | `c0e0a0f01023d5e701c13bcd092d23ef216dd3e96b2bc0320293c355252df23f` |
| Independent audit source | `6f642659d1bc7de2956109c513da8339a4f34ec8e4740bf34c242e4b09d5f0fa` |
| Independent audit JSON | `a4f9095afe0cd1c065cc788c8d2249396d39e4d563fb2b6d7db8430ff16e3172` |

Pilot files are under `artifacts/benchmarks/learned-numerical-pilot-20261006T0131/`;
the original evaluation is under
`artifacts/benchmarks/learned-numerical-evaluation-20261006T0133/`. Full per-job
comparison, NPZ, native input/component and generator-truth hashes are retained
in the adjacent audit JSON. Twenty-nine bound files were read and rehashed at
the end, with unchanged bytes. Every NPZ was loaded with `allow_pickle=False`;
all note/onset/contour tensors were finite, in `[0,1]`, and of expected shape.
Source WAV bytes were hashed, never decoded to samples.

The fixed four jobs remain 8/8/6/8 analyzed seconds, 19 windows, 2,580 retained
rows and 4,623,360 raw numeric bytes. Full native source extents are separately
8/8/10/10 seconds: the last two unrequested tails do not enter these metrics.

## Independently reproduced scores and support

The audit implements its own generator-region/trajectory/absence lookup,
window geometry, deterministic lowest-MIDI top-one choice, fixed 0.3 voiced
threshold, ±50-cent raw/chroma tests and octave classification. It does not
import either metric evaluator or the discovery worker. Reported numerators,
denominators and null values were compared against independent calculations.

| Native whole-input context | Rows |
| --- | ---: |
| Input zero padding | 1,018 |
| Crossing reference/condition boundaries | 1,006 |
| Polyphonic center, separately excluded from monophonic scoring | 130 |
| Stable monophonic, entirely from missing-F0 C1 | 426 |
| Stable guitar absence | 0 |
| Total | 2,580 |

Missing-F0 native pitch accuracy is **34/426 = 7.9812%**. Chroma is **426/426**;
octave errors are **392/426 = 92.0188%**. The eligible top-one MIDI histogram is
exactly C1/MIDI24:34 and C3/MIDI48:392, a two-octave substitution. All 426
eligible rows are above the fixed activation threshold. Ladder, legato and
sweep native monophonic denominators are zero; their raw/chroma accuracy is
null. Native absence false-alarm rate is also null with N=0 throughout. These
nulls are reproduced rather than converted to zero errors.

| Pointwise model-clock label view | Correct pitch / monophonic N | False voiced / guitar-absent N |
| --- | ---: | ---: |
| Missing-F0 | 65 / 605 | 0 / 83 |
| Tuning ladder | 405 / 466 | 46 / 222 |
| Legato/glide mixture | 357 / 423 | 2 / 93 |
| Sweep/polyphony mixture | 254 / 297 | 23 / 261 |
| Aggregate | 1,081 / 1,791 | 71 / 659 |

Pointwise raw pitch accuracy is **60.3573%**, chroma **1,607/1,791**, and
false guitar voicing **10.7739%**. True-voiced abstentions remain in the
denominator (1,645/1,791 are estimated voiced). The 130 chord-centered rows
remain outside the monophonic pointwise denominator. Pointwise timing labels
do not establish full-input support or comparable short-window resolution.

Uncalibrated maximum-activation means over all rows are 0.381646/0.479037/
0.531986/0.430532 by case; missing-F0 C1-bin mean is 0.229451. These are raw
activation measurements, not probabilities of correct notes. Every decoded
event mean-note and maximum-onset activation was independently recalculated
from its raw pitch-column `[start,end)` slice, agreeing within `1e-7`.

## Clocks, events and prediction-before-truth scope

All three saved clocks exactly matched independent sample arithmetic (maximum
absolute residual zero at stored precision), including their different seams:
nominal hop `i*256/22050`; model time subtracts
`floor(i/172)*((172*256-43844)/22050+0.0018)`; input projection uses retained
window stride 36,164, prepend 3,840, crop 15 and retained width 142. Window
index/frame-index arrays and each input window's leading/trailing zeros and
context extents also matched. Native input support was determined independently
from these windows and truth intervals. No clock was fitted, shifted, warped
or chosen for better scores. Alternative nominal/projection pointwise counts
and raw/chroma/octave/absence rates also reproduced the original receipt.

All supplied project event identities were reconstructed from saved arrays at
fixed thresholds and corrected elapsed floors. Their model endpoints and
activation summaries agreed. An independent augmenting-path matcher reproduced
maximum-cardinality onset-only TP/FP/FN at the declared 50 ms/50 cent tolerances;
this readback does not independently reproduce minimum-cost tie assignment or
all signed/offset residual distributions. Those algorithm/boundary mechanics
were covered by the prior [source audit](2026-10-06-learned-pitch-code-audit.md).

| Generated cohort | 127.7 ms events; TP/FP/FN | 25 ms events; TP/FP/FN |
| --- | --- | --- |
| Missing-F0, one generated reference | 9; 0/9/1 | 12; 0/12/1 |
| Ladder, nine generated references | 16; 7/9/2 | 19; 7/12/2 |
| Legato, five requested generated references | 5; 5/0/0 | 9; 5/4/0 |
| Sweep cohort, eighteen generated references | 13; 7/6/11 | 33; 15/18/3 |
| Event totals | 43 | 73 |

The short floor adds sweep recall and false positives. A 25 ms duration rule is
not 25 ms low-fundamental resolution; neither preset is selected as a winner.
Synthetic generated-score transitions are not an intended score for a person.

The predictions-only freeze binds all four comparison/NPZ hashes, declares
`truth_content_read:false`, and is referenced by the later truth-bound index.
The inspected controller command supplies only an opaque job directory, start,
budget and fixed thresholds. Controller source writes the predictions freeze
before assembling the truth-path index and does not read truth content or call
evaluation. Its preparation reads bank/pYIN/preregistration metadata, so this
claim concerns **discovery receiving no truth content**, not a claim that all
orchestration metadata is absent. The generic `denoised.wav` aliases are exact
native component bytes; their manifests explicitly record that no denoising
was performed. Runtime receipt ordering is supported by controller source and
sealed artifacts, not a fresh replay or independent process-level recording.

The evaluated receipt retains generator-only scope, zero unsupported claims,
real-performance/listening flags set to false, quality alerts, and separate native,
pointwise and alternative-clock denominators. No actual-take, harmonic-repair,
fret/string, missed/rushed-note, or automatic winner conclusion follows.

## Reproduction and handoff

```sh
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  .venv/bin/python docs/agent-notes/2026-10-06-learned-pitch-numerical-audit.py
```

The harness prints a bounded JSON readback and writes no files itself. Its
captured adjacent JSON contains only hashes and numerical diagnostics. The
audit readback is frozen before root's separately planned relative-CLI-path
normalization fix. Any new source hash or new MCP proof is separate from the
original `1fb883...` evaluation and must not relabel this frozen receipt.
