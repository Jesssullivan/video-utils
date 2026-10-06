# Actual low-register diagnostic: independent timing audit

Actor `media_latency`; authority root's source/metadata-only assignment,
R-HOOK-CONVERGENCE-20261004 and R-N13. This audit owns this dated note only.
The diagnostic controller, frozen DSP worker, source PCM, original video,
masters and current renders are outside its mutation scope.

Plan before audit: bind the proposed plan and controller/worker hashes, derive
the native sample and hop-grid arithmetic independently, trace padding and OLA
support, verify capture full-frame count and Welch frame membership, and check
processed/residue extents. Read code and metadata only; no actual PCM, DSP,
render or source mutation. Report a meaningful must-fix promptly to root.

Definition of done: a hash-bound verdict with exact arithmetic and limitations.
Any positive timing result is not actual execution, noise-only capture proof,
isolated fan/music separation, listening acceptance or default adoption.

Verdict: positive independent **timing/support-only** audit; no timing must-fix
found. This result does not replace the separate mask/metric audit or the exact
root execution release required by the controller. Reviewed identities:

- Controller SHA256 `2b84f9f7f7b49b691cec68b83546fbf378fa172296e6339aa03c5552fc42c284`.
- Frozen DSP worker SHA256 `384a99bca9e72212b5d9631e9b425424ea7b08fc41ce6eb4dde4d647b3ba3bc6`.
- Plan SHA256 `ed664a3898ec1e25103fa9062567078cbc2326d4fa01346d9b45565ebda46b75`:
  `artifacts/experiments/low-register-actual-diagnostic/plan-20261006T0110-v2.json`.

The metadata-only `declaration()` exactly matched the frozen plan's canonical
JSON. It checked the frozen worker/comparison and current manifest hashes, not
the original video or PCM payload. Native rate is 44,100 Hz, one channel, decoded
origin zero; the registered decoded extent is 6,657,385 frames. Those native
metadata assertions are source-bound, not new source decode evidence.

Independent standard-library integer enumeration confirms:

| Quantity | Exact result |
| --- | --- |
| Diagnostic source span | [882000,1323000), 441000 samples = 10 seconds |
| Synthetic prefix | 882000 mod 2048 = 1360 samples |
| Padded analysis input | 442360 samples; sample zero maps to source 880640 |
| Worker right padding | 8200 samples (8192 plus 8 grid-alignment samples) |
| Mask frame grid | 221 starts from 872448 to 1323008, each divisible by 2048 |
| Fully original-supported mask frames | 211, starts 882688 through 1312768 |
| Reviewed capture | [180810,218295), 37485 samples = 0.85 seconds |
| First capture frame | 182272; 1462 leading samples excluded from fitting |
| Complete capture frames | 14; last start 208896, last end 217088 |
| Capture remainder after last complete frame | 1207 samples, unused in fitting |
| Conservative metric span | [890191,1314809), 424618 samples |
| Welch source-grid frames | 203; first start 890880, last start 1304576, last end 1312768 |

The synthetic prefix aligns the worker's existing centered padding to source
sample-zero's hop grid without reading actual context outside the excerpt.
`frame_native_starts` are translated by `882000 - 1360`; the support flags check
both original excerpt boundaries. Centers are starts plus 4096, never relabelled
as phrase, note or onset times. Padded mask frames remain explicitly distinct
from frames with complete original support.

The 8191-sample guard on both sides is conservative for an 8192-sample frame.
Every OLA frame contributing to either endpoint of the half-open metric span
is fully contained in the original excerpt: extreme contributing starts are
882688 and 1312768, whose right extents are at most 1320960. All intermediate
contributors likewise have original support. Welch frames start on the original
2048-sample grid, remain fully inside the guarded metric span, use the periodic
Hann with no detrending, and pair source/output frames without a fitted shift.
Coherence is a Welch per-bin calculation; mixture band-power change separately
uses the worker's longer guarded-interior Hann estimate. Neither is isolated
fan reduction or musical-component gain.

`apply_frozen_gain` reconstructs and trims back to the extended input's native
extent, then the controller selects `[1360:442360)`, exactly 441000 samples.
Residue is `original_excerpt - processed` on that same one-channel native array;
the support and metric clocks remain source-relative. Saved `.npy` output and
residue are reversible diagnostic arrays, not normalized delivery audio or
recovered stems. No source time stretch, rate conversion, EQ, compression,
normalization or media export appears in this controller.

This review performed source reading, current metadata reading and integer
support enumeration only. It did not open original/PCM payloads, invoke a DSP
worker on audio, execute the diagnostic, create an execution release, or change
any original/master/run/render/latest artifact. The fixed reviewed capture may
contain music; its fourteen full frames establish estimator support only.
Actual output identity, residue values, hard deadline enforcement, listening
quality and applicability require their separate execution/audit evidence.
