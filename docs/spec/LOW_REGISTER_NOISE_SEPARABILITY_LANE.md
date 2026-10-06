# Low-register noise separability and preservation lane

Authority: the operator's authorized restoration/research goal, repository
`AGENTS.md`, R-HOOK-CONVERGENCE-20261004 and R-N13. Owner of this specification
and its dated research receipt: `audio_research`. This is a bounded next-stage
design, not authorization within this lane to change core workers, registered
profiles, source audio, candidate renders, host configuration or published pilot
receipts. Root owns implementation assignments, actual renders and acceptance.

## Problem and evidence boundary

The guitar intentionally reaches approximately 32 Hz; its constant tuning is
C1 F1 Bb1 Eb2 Bb2 Eb3 Ab3 C4 F4. A fan and guitar can occupy the same frequencies.
Neither stationarity, a quiet-looking video frame, low RMS nor proximity to a
known open-string frequency proves that energy is unwanted.

Frozen actual-source SHA256:
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.
The existing capture is 4.10–4.95 seconds relative to decoded audio sample zero;
it was selected for review, not verified noise-only audio. Captured8 reduces
4–5-second total pre-gain RMS by 4.445 dB. Its active-window 20–45 Hz mixture power
falls approximately 2.04–2.76 dB, while 45–120 Hz falls about 0.086–0.196 dB.
These are measurable mixture changes, not isolated fan reduction or low-note gain.
Source/denoise coherence around 0.95 in the low band does not prove unity gain.
The frozen evidence is in the dated captured-restoration comparison/segment
JSON and Markdown receipts; retain their exact hashes in any subsequent result.

The complementary box-fan characterization uses only 0.85–1-second windows,
16384-sample Hann Welch estimates at 44.1 kHz, 2.69165 Hz bins and three/four
overlapped averages. It does not resolve a distinct 32.7 Hz peak or physical fan
linewidth. Approximately 78/156/312 Hz structure can also resemble an Eb2 harmonic
comb. A spectral resemblance is not a fan RPM estimate, played-note identity or
proof of capture contamination; it establishes an ambiguity to test.

## Relevant methods and limitations

[FFmpeg afftdn](https://ffmpeg.org/ffmpeg-filters.html#afftdn) exposes captured
noise shape, reduction, floor, tracking and smoothing controls. The reviewed
[upstream source](https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/libavfilter/af_afftdn.c)
uses approximately 37.5 ms windows and fifteen profile centers starting at 80 Hz.
Those coarse controls are not an independent 32 Hz surgical mask. Check the
installed/pinned implementation before using this source observation as a
version-specific claim. A `noise_floor=-40` setting is a control, not a measured
absolute PSD or a calibrated noise floor for this take.

[Martin's minimum-statistics estimator](https://www.iks.rwth-aachen.de/fileadmin/publications/martin01c.pdf)
tracks smoothed spectral minima instead of relying on a speech activity detector.
For guitar, sustained harmonics can remain in those minima, so automatic tracking
can learn wanted sustain as noise. Begin with a fixed reviewed capture; evaluate
tracking as a separate experiment rather than an implicit default.

[Ephraim–Malah MMSE-STSA](https://malah.net.technion.ac.il/files/2017/08/Ephraim_Speech_Enhancement_ASSP84.pdf)
estimates speech spectral amplitudes under an additive statistical model.
Wiener/MMSE gains are model-dependent estimates; they cannot make coincident
fan/guitar components identifiable. Distorted harmonics and long musical tails
require preservation tests rather than a speech-presence decision.

[Harmonic/percussive median filtering](https://dafx10.iem.at/papers/DerryFitzGerald_DAFx10_P15.pdf)
separates spectrogram geometry, not wanted versus unwanted sources. A steady fan
line and guitar sustain can both look harmonic; a pick and a click can both look
percussive. Use geometry as an uncertain protection cue, not a recovered stem.
[RNNoise](https://jmvalin.ca/demo/rnnoise/) and
[DeepFilterNet](https://arxiv.org/abs/2110.05588) target speech. Their pitch/periodic
processing is not evidence of nine-string distorted-guitar preservation. No
speech model, download or resynthesis is part of this design's default.

## What one mixture cannot establish

For an additive mono observation `x = s + n`, any `u` produces the same observation
as `(s + u) + (n - u)`. Source priors or references are required to choose a split.
An exact-frequency fan tone and sustained C1 note are a deliberate non-identifiable
negative control. Leaving ambiguous energy is a valid preservation outcome;
report remaining noise rather than inventing a clean guitar stem.

An independently recorded fan sample helps estimate spectral statistics, not the
instantaneous phase/waveform of the fan in this take. A contemporaneous noise
reference microphone can help only where its transfer/coherence assumptions hold.
A DI track offers much stronger musical reference but has its own amp/room/codec
mapping. Operator-confirmed muted-string fan-only spans, longer same-device
captures and fan-off comparison takes improve evidence without being mandatory
inputs for today's reversible comparisons.

If phone/Photo Booth AGC or nonlinear compression occurred, a quiet capture may
not transfer unchanged to active passages: `x(t)=a(t)[s(t)+n(t)]` changes apparent
noise level with the unknown gain. Clipping can destroy information. Existing
level/shape differences do not establish that AGC occurred or identify its gain.
Never call a normalization/EQ gain change improved SNR.

## Bounded next-restoration comparison

Keep bypass and frozen captured8 as immutable comparators. First prototype an
explicit continuous low-register protection variant; a quieter whole-mixture
number alone cannot select it. Rust remains the reusable DSP target, FFmpeg
owns decode/export, and existing locked Python/NumPy/SciPy may support a bounded
offline experiment. No new dependency or model is required by this specification.

Proposed controls, not current public-tool parameters:

| Control | Initial bounded comparison |
| --- | --- |
| Capture | Exact source-bound existing interval; fixed PSD, no automatic tracking |
| Low-region attenuation ceiling | 0 or 0.5 dB amplitude reduction across 20–80 Hz; explicit taper to ordinary denoise behavior over 80–140 Hz |
| Spectral gain floor | For the 0.5 dB variant, `G >= 10^(-0.5/20)` in the protected region; this is a bin-gain bound, not an already-proven musical-gain bound |
| Broadband reduction | Compare existing 6/8 dB-strength controls; record measured effects separately from requested reduction |
| Noise PSD scale | Compare fixed 0.5/1.0 scale hypotheses; flag inadequate capture support and cross-interval drift |
| Harmonic protection | Optional second experiment: multiple mixture-derived pitch/periodicity hypotheses; widen protection, never declare notes or remove ambiguous energy |
| Windows | Record native-rate frame/hop, taper, padding and OLA reconstruction; compare longer low-frequency context against transient smear explicitly |

A custom STFT prototype can use a nonnegative Wiener-style gain
`G = P_s / (P_s + lambda * P_n)`, with a documented estimate of `P_s` from the
mixture and a fixed captured `P_n`, then impose the protection floor. Save the
actual gain mask and settings. Reuse mixture STFT phase; native-waveform timing,
attack support and tail behavior still require tests. This is a proposed estimator,
not a claim that the supplied capture is pure noise or its PSD is known exactly.
Longer windows improve spectral discrimination while reducing temporal precision;
zero padding refines displayed bin spacing without creating observed duration.

Protect uncertain low content continuously. Do not secretly bypass selected
transients or switch off processing in inconvenient test regions. No default
high-pass, mains notch, fixed 32 Hz removal, harmonic deletion, transient editing,
note-correctness grading or intended-score input is permitted. Low protection may
retain low fan energy; expose that tradeoff in the output/receipt. Offline window
and delay choices are not automatically suitable for an AU render callback.

## Separability experiment and truth accounting

Use a new, separate eight-case bank, at most eight seconds each (64 seconds total),
with bounded native-rate mono/stereo coverage and 44.1/48 kHz integrity controls.
Keep the published pitch/phrase bank/pilot immutable. Each new fixture saves
clean guitar, fan/noise, mixture, exact sample extent, generator settings and
hashes; truth enters only evaluation after a mixture-derived mask is saved.
Synthetic capture/profile receipts must bind their own fixture inputs. Do not
transplant the actual take's captured profile or spoof its original source hash
to make fixture processing run. Matched numeric controls are a separately tagged
synthetic experiment, not the actual source-bound captured8 invocation.

| Case | Required distinction |
| --- | --- |
| Clean C1 sustain plus harmonics | Clean-only processing damage and tail/phase behavior |
| Fan-only colored/tonal noise near 32 Hz | Actual noise-only reduction, absence of fabricated guitar |
| C1 and fan at exactly the same frequency, varied phase | Non-identifiable collision; preservation must not be mislabeled successful separation |
| C1 with a spectrally separated fan line | Distinguishable control versus the coincident case |
| Walking C1/F1/Bb1/Eb2 over stationary fan | Do not learn wanted moving or sustained fundamentals as noise |
| Palm mutes and quiet decays with fan | Attack area, onset timing, tail support, pumping and musical-noise review |
| Missing-F0 harmonic proxy with fan at theoretical F0 | Do not synthesize missing fundamentals or equate a fan line with a played note |
| Time-varying fan level and declared synthetic gain envelope | Capture-transfer mismatch; preserve source references and label the gain model synthetic |

For a mask-based worker, derive the mask from the mixture only and freeze it.
Then apply that **same mask** to oracle guitar/noise STFT components during
evaluation. This gives conditional component accounting for the actual applied
linear mask, even if mask estimation was nonlinear. Verify reconstructed
`masked_guitar + masked_noise = masked_mixture` within numeric tolerance. Noise
attenuation and guitar distortion are measured separately; truth must never
choose the mask, pitch branch or protection region during discovery.

For black-box afftdn, `D(s+n)-D(n)` is only an incremental response: input-dependent
processing prevents treating it as an isolated guitar output. Report clean-only
damage, noise-only reduction and mixed-reference error separately. A projection
onto a known guitar sinusoid can contain coincident/correlated fan energy; it is
not an independent source gain in the collision case. Whole-mixture low-band power,
coherence and fitted SDR remain useful diagnostics with those limits.

## Adoption tests and stop conditions

Gate adoption on native extent, source/hash identity, bypass reconstruction,
finite outputs and documented delay; do not fit a convenient posthoc time shift
or loudness correction into preservation scores. Independently recompute known
musical component gain/error where component accounting is available. Proposed
initial preservation gate: no more than 0.5 dB coherent fundamental attenuation
on clean-only/identifiable C1 controls; report octave/harmonic and palm-mute/tail
metrics rather than substituting a mixture-energy ratio. Final numeric attack/
tail tolerances must be recorded before comparative execution.

Select candidates on a Pareto comparison of noise-only reduction versus musical
damage, including held-out SNR, line offset/phase, distortion and decay settings.
The exact-collision fixture is not required to meet contradictory source-removal
and source-preservation targets. Report abstention/remaining noise instead.
An actual-take candidate requires source-time A/B listening and residue review
on low-string sustains, walking notes and palm mutes. A reviewed noise interval
and a good synthetic score cannot establish real musical transparency.

Bound each future worker to two numerical/FFmpeg threads, at most 120 seconds,
no downloads and new ignored output directories. A first actual comparison may
use at most ten seconds of decoded original audio for diagnostics; no new actual
candidate or core change was executed by this research lane. Record all controls,
source/capture/mask/output hashes, applicability, observed coverage and unresolved
separability. Root reviews concrete evidence before adopting a default.
