# Basic Pitch comparator source review

Actor: `/root/clip_baseline/mir_sources`; checkpoint 2026-10-05 23:59 UTC.
Authority: operator-authorized parallel project work, root's named receipt
assignment, repository AGENTS.md, R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13.
Scope: read-only source/research review plus this owned receipt. No package
imports, installations, downloads, model sessions, audio inference, registry
changes or duplicate runtime qualification were performed.

The inspected project adapter is `scripts/basic_pitch_compare.py`, SHA256
`e69d943e01489fe364b48b212fe5c7ce12101279cd136464d2d5d616bf818baf`.
It uses the official qualified model with **project threshold-run decoding**;
upstream postprocessing parity is explicitly false. The live owner may revise
this source after the checkpoint; these findings bind this snapshot only.

## Four primary pointers

- [Pinned 0.4.0 constants](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/constants.py):
  22,050 Hz mono, 256-sample nominal hop, 43,844-sample input, 172 declared
  frames, 88 semitone bins beginning at 27.5 Hz. C1 is representable, not
  validated. Its theoretical A440 period is approximately 30.578 ms.
- [Pinned inference](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/inference.py):
  upstream prepends 3,840 zero samples, steps 36,164 samples, pads short final
  windows, removes 15 output frames from each side, joins 142 retained rows
  per window, then crops to `floor(original_samples * 86 / 22050)`. The inspected
  adapter implements these arithmetic rules, but uses FFmpeg analysis resampling
  rather than upstream `librosa.load`; resampler parity is not established.
- [Pinned note creation](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/note_creation.py):
  upstream adds inferred onsets, processes onset peaks backwards, tolerates
  short low-energy gaps, suppresses neighboring bins and optionally applies
  residual-energy Melodia recovery. The project starts threshold-active runs,
  closes them immediately below threshold, and splits on local model-onset
  peaks; it omits those other operations and pitch-bend decoding. These are
  different event estimators, even when they reuse identical model arrays.
- [librosa 0.11.0 SuperFlux example](https://librosa.org/doc/0.11.0/auto_examples/plot_superflux.html):
  a transparent onset comparator using maximum-filter vibrato suppression.
  Its 5 ms hop is not per-note accuracy or pitch resolution. Compare sustained
  vibrato, weak legato attacks and picked attacks separately; it cannot establish
  missed notes from absent onset peaks.

## Clock and duration oracles

The upstream event clock is nominal `index*256/22050` minus
`floor(index/172)*0.010326077097505667`. This empirical correction is separate
from physical latency and from retained-window sample provenance. At retained
row 142, nominal/upstream time is 1.648616780 s while the second retained
window's sample origin is 1.640090703 s. At row 172 the upstream event clock is
1.986590023 s versus window provenance 1.988390023 s. Preserve all three axes
and test each seam; do not fit a correction from generated truth.

Upstream rounds milliseconds to frames and rejects lengths less than or equal
to that result. Thus 25 ms rounds to two frames and requires three nominal
hops (34.829932 ms); 127.7 ms rounds to eleven and requires twelve
(139.319728 ms), away from clock corrections. The project instead compares
corrected elapsed duration directly with an inclusive floor. It permits eleven
hops (127.709751 ms) at its default. A three-hop interval crossing a correction
boundary lasts 24.503855 ms and fails the project's 25 ms floor; four hops last
36.113832 ms. A duration control is not model analysis resolution.

The inspected source saves only corrected `model_times_seconds`, generic
padding/window constants and event frame indices. Explicit per-window trailing
padding, retained-row provenance, nominal clock and clipping reasons remain
source-review gaps at this checkpoint. Model runtime qualification remains the
existing owner's evidence, separate from adapter/metric acceptance.

## Benchmark consequences and coordination

The existing zero-window runtime smoke has positive note activations
0.0936–0.1607, below the fixed 0.3 threshold. This establishes neither a false
decoded note nor pitch accuracy: unconditional argmax still returns a pitch on
absence, so publish abstention and false-voicing denominators. No new zero-input
session was run. Smoke-receipt SHA256:
`3bd5a87752d6927919dce1429865e84b4678abd28c3bbb055eefcb82ab8026f2`.

The fixed acceptance cohorts must retain missing-F0 C1, harmonic/octave errors,
80 ms sweep omissions/merges, glides without picked attacks, chord cardinality,
absence, excerpt boundaries and every window seam. Approximately two-second
model inputs do not establish effective receptive-field duration. Treat native
context scoring, paired timestamps and event matching as distinct views.

Findings were sent to `tonal_inference` and `guitar_features`; the latter owns
the existing [acceptance specification](../spec/PITCH_COMPARATOR_ACCEPTANCE_LANE.md).
That specification's inspected SHA256 is
`22d8f7deff18bd808035acc7f3ba7b1c89eea1e79832d0ef4b4456aad2749c2a`.
Its 30-second generated cohort remains fixed. Real-take differences are review
candidates, without played-note correctness or listening acceptance.

## Pure evaluator appendix, October 6 00:27 UTC

Root reattached this lane for source review supporting `guitar_features`' new
pure learned-pitch evaluator. Authority and write scope remain unchanged. The
updated adapter SHA256 is
`8bc17166c48ff6dccf33fd0eb17d3257535d6d91c83df0afed51b9c59dc75ee1`;
its test source SHA256 is
`c71400db31f0e5032897cf6a20836f297d4fa72863a188c395fa147c10be66e6`.
These are source-read identities, not an independently executed test result.

The adapter now writes nominal, empirical-model and input-window-projection
times, window indices/frame indices, and per-window padding/crop/context maps.
Those additions resolve the absent-axis and per-window metadata gaps identified
at the earlier snapshot; the original checkpoint is retained as history. The
project decoder still differs from upstream, including its elapsed-duration
floor. Its identity and controls must bind evaluator receipts, not merely the
official model hash.

Independent evaluator pitfalls relayed to `guitar_features` and `tonal_inference`:

- Derive retained counts from original decoded samples and the declared
  `floor(N*86/22050)` rule. Do not replace this with division by the nominal
  256-sample hop. Verify all three axes and window-row mapping before metrics;
  sensitivity views must be predeclared rather than selected by best score.
- Context eligibility uses the original window extent and both zero-padding
  counts. Already-clipped `input_context_*` bounds cannot prove complete input
  support. The recorded three-second generated smoke has two padded windows
  per case and zero wholly unpadded rows. Native full-window accuracy is null
  with N=0; pointwise diagnostics remain a separate, explicitly weaker view.
- An event's exclusive end index may equal the retained count, where no output
  row exists. The adapter then extrapolates the last projection plus one hop;
  its empirical endpoint uses `frame_time(end_index)`. Validate these rules
  explicitly. Preserve raw endpoints, decoded coverage and clipped display
  endpoints separately; never score artificial continuation beyond coverage.
- A single event crossing multiple windows needs the union of their input
  supports for conservative context eligibility. A valid start row alone does
  not qualify its end, silence gap, onset, or full duration. Keep truncated
  boundary events and reference events in separate denominators rather than
  deleting unmatched events.
- Top-one pitch requires a separate fixed activation/absence rule: positive
  sigmoid activations on zero input do not themselves establish voiced notes.
  Keep abstentions in true-voiced denominators, false voicing in absence, chord
  set cardinality, and octave-versus-chroma agreement distinct. Activation and
  decoded amplitude are not calibrated musical confidence.

The corrected smoke generator constructs missing-F0 from **linear harmonics
2 through 8 of C1**, with no fundamental coefficient or tanh. Consecutive odd
and even integer harmonics retain C1 periodicity; there is one generated C1
voice, not seven reference notes. An estimator selecting C2/C3/C4 may track
present spectral partials while failing the declared note-pitch task. Such
outputs belong in octave/extra-harmonic diagnostics, without truth-guided
harmonic suppression. This mathematical construction does not establish what
a listener hears or what an actual nine-string player performed. Nonlinear
processing can create intermodulation components, so the earlier nonlinear
proxy cannot be treated as the same missing-F0 condition.
[UNSW Music Acoustics explains missing-fundamental pitch](https://phys.unsw.edu.au/jw/musFAQ.html)
and distinguishes [ideal harmonic ratios from real string inharmonicity](https://phys.unsw.edu.au/jw/harmonics.html).
Those physical differences are a reason to retain real-guitar listening and
annotation acceptance separately from finite, exact-harmonic synthetic tests.

Read the existing immutable smoke's support metadata and the current generator
source only. The independently reported 0/258 C1 top-one membership and partial
histogram remain `guitar_features`' numerical readback; this lane did not load
NPZ arrays or reproduce model inference. Stepped, phase-discontinuous proxies
still do not validate physical sweeps, taps or continuous legato. No new
performance score, model session, audio decode or runtime claim was introduced.
