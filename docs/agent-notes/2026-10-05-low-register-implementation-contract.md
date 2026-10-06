# Low-register prototype implementation contract and synthetic receipt

Actor: `audio_research`. Authority: root's reattached documentation-only lane,
repository `AGENTS.md`, R-HOOK-CONVERGENCE-20261004 / R-N13. Exclusive write:
this new appendix. The frozen [separability specification](../spec/LOW_REGISTER_NOISE_SEPARABILITY_LANE.md)
and [primary research receipt](2026-10-05-low-register-noise-separability-research.md)
remain the design basis. This declares a possible first offline prototype;
it does not publish or admit a default DSP method, profile or AU control.
Root explicitly released only the new offline prototype worker/tests after this
appendix draft, with synthetic execution following fixture freeze and independent
audit. Actual-take audio and public/default DSP remain unreleased in this lane.

## Ownership and first comparison

`clip_baseline` owns the separate fixture generator/declaration and independent
fixture audit (`scripts/low_register_fixtures.py`, its named tests and its root-
assigned receipt). This appendix owns interfaces, equations and proposed metric
thresholds. The generator's frozen declaration is the sole authority for exact
amplitudes, phases, event envelopes and sample indices; do not invent a second
truth table here. Root owns any future worker assignment, actual candidate and
integration. Published pitch/phrase fixtures, scores and pilot receipts stay
unchanged. No actual audio was decoded by this appendix lane.

Freeze four first-comparison settings before running any result:

| Variant | Low attenuation ceiling | Noise-density scale | Broadband ceiling |
| --- | --- | --- | --- |
| P0-N05 | 0 dB | 0.5 | 8 dB |
| P0-N10 | 0 dB | 1.0 | 8 dB |
| P05-N05 | 0.5 dB | 0.5 | 8 dB |
| P05-N10 | 0.5 dB | 1.0 | 8 dB |

Also save all-one-mask bypass. Frozen captured8 is an actual-take comparator,
not a synthetic profile whose source hash may be substituted. A later 6 dB
comparison requires a new recorded declaration; the first four settings hold
broadband strength constant. No tracking, smoothing, pitch inference, harmonic
branch, dynamics, EQ or transient switching belongs to this first matrix.

## Exact processing boundary and signatures

The following declared Python interfaces guided the bounded NumPy prototype
released later in this receipt. The actual worker adapts its evaluator signature
to caller-verified component arrays and canonical fixture truth. Reusable DSP is
ultimately Rust-owned. All arrays are finite, contiguous float64/complex128;
time-domain layout is `[sample, channel]`, spectra/gains `[frame, channel, bin]`.
Native sample rate/channels are preserved. Reject empty/nonfinite arrays,
unsupported rates/channels, malformed intervals and mismatched clocks/shapes.
Nothing resamples, changes sample origin or adjusts presentation loudness.

```python
@dataclass(frozen=True)
class MaskConfig:
    sample_rate: int                 # 44100 or 48000 for this experiment
    frame_samples: int = 8192
    hop_samples: int = 2048
    protected_end_hz: float = 80.0
    taper_end_hz: float = 140.0
    low_ceiling_db: float = 0.5      # exactly 0.0 or 0.5
    broadband_ceiling_db: float = 8.0
    noise_density_scale: float = 1.0 # exactly 0.5 or 1.0

def fit_capture_density(
    capture_pcm: NDArray[float64], *, config: MaskConfig,
    source_sha256: str, decoded_start_sample: int,
    decoded_end_sample: int,
) -> CaptureDensity: ...

def analyze_native(
    pcm: NDArray[float64], *, config: MaskConfig,
) -> NativeFrames: ...

def derive_gain(
    mixture_frames: NativeFrames, capture: CaptureDensity, *,
    config: MaskConfig,
) -> FrozenGain: ...

def apply_frozen_gain(
    pcm: NDArray[float64], gain: FrozenGain, *, config: MaskConfig,
) -> NDArray[float64]: ...

def evaluate_known_components(
    *, fixture: VerifiedFixture, frozen_gain: FrozenGain,
    processed_mixture: NDArray[float64], thresholds: FrozenThresholds,
) -> ComponentMetrics: ...
```

`CaptureDensity` contains `[channel, bin]` density, full-window count, native
capture indices, source/decoded-PCM hashes, window/config hash and unit string.
For an excerpted actual comparison, indices still bind decoded full-source
sample zero; the discovery worker receives a reviewed capture, not clean/noise
references. Each synthetic capture binds its own mixture source. Require at
least four fully contained capture frames, no padded capture frames, and record
their overlap/support. A contaminated or changing capture remains a hypothesis.

The declared complete frame contract comprises complex coefficients, original
sample extent, left/right padding, every frame's native start/center and
full/partial support. The first prototype's `NativeFrames` stores exact starts
and grid/padding in memory; exported receipts store grid, extent, padding and
frame count. Centers and support flags are reconstructible from those fields
but are not exported as separate per-frame arrays in this revision.
`FrozenGain` contains real float64 gains, the exact frame grid/config/density
hashes and opaque mixture identity. `apply_frozen_gain` validates the same native
extent/channel/grid; it does not derive a new mask from a component. Evaluation
receives known components only after mask/output hashes are committed.

## Fully specified analysis, density and reconstruction

Use periodic Hann `w[j] = 0.5 - 0.5*cos(2*pi*j/L)`, `L=8192`, `H=2048`.
Use unscaled forward `rfft(..., n=L, norm="backward")` on `w*frame`; invert with
`irfft(..., n=L, norm="backward")`. Native bin centers are `k*fs/L`. These are
approximately 5.38/5.86 Hz bins and 185.76/170.67 ms windows at 44.1/48 kHz;
nearby lines remain unresolved when observation/window support is insufficient.
Zero padding does not create independent low-frequency evidence.

For processing, prepend exactly `L` zeros. Append `L` zeros plus the smallest
nonnegative integer `e` making `N+L+e` divisible by `H`. Traverse starts
`0,H,...,padded_length-L`; native starts are padded starts minus `L`.
Reconstruct by accumulating `irfft(gain*X)*w` and dividing by accumulated `w*w`.
Require positive normalization across the retained `L:L+N` samples, then crop
exactly those samples. For all-one gains the complete source, including edge
samples, must reconstruct. Record lookahead/window support; offline zero-origin
cropping is not proof of a causal or callback-safe AU implementation.

Estimate capture density from unpadded fully contained frames. For each channel:
`Pn[k] = mean_frames(c[k]*abs(X[k])**2 / (fs*sum(w*w)))`, with `c=2` for interior
positive-frequency bins and `c=1` for DC/Nyquist. Units are full-scale-squared/Hz,
not dBFS, a fitted note amplitude or an afftdn `noise_floor` parameter. Mixture
frame density `Py` uses the identical convention. Do not subtract a frame mean,
normalize capture/source separately or pool stereo channels implicitly.

Set `Q = noise_density_scale*Pn`, `Ps=max(Py-Q,0)`,
`Graw=Ps/(Ps+Q+1e-24)`; where `Q==0`, set `Graw=1` explicitly. Then impose a
frequency-dependent floor. Let `b=10**(-8/20)` and
`l=10**(-low_ceiling_db/20)`. Use floor `l` from DC through 80 Hz; over 80–140 Hz
use `b+(l-b)*(1+cos(pi*(f-80)/60))/2`; above 140 Hz use `b`.
`G=max(Graw,floor)` and validate `floor<=G<=1`. Extending protection through DC
avoids an undeclared below-20-Hz removal stage; it does not assert that DC is
music. The floor is an STFT-bin constraint, not a proven waveform/source-gain
bound. No automatic noise learning or undeclared frame exceptions are allowed.

Save pre-gain processed float PCM and `mixture-processed` residue, mask/density
arrays, frame metadata and all hashes before scoring. No normalization, limiter,
clipper, dither, alternate phase or automatic delay fitting enters these outputs.

## Canonical owned fixture construction requirements

Eight fixtures are eight seconds each, 64 seconds total. The independent owner
declares native sample indices, gains, phase, randomness algorithm/seed, allowed
harmonics, event/window applicability and component hashes before generation:

| Case | Native format and mandatory oracle |
| --- | --- |
| Clean 32.000 Hz sentinel and theoretical C1 harmonic proxy | 44.1 kHz mono; separate simultaneous frequencies/segments explicitly; noise exactly zero |
| Fan-only colored/tonal noise including a C1-near line | 48 kHz mono; guitar exactly zero; no fabricated guitar label |
| Exact theoretical-C1 guitar/fan collision | 48 kHz stereo; fixed distinct per-channel phase; same observed mixture also supports an explicit alternative component assignment |
| Spectrally separated theoretical C1 and 113 Hz fan | 44.1 kHz mono; the frozen fixture owner selected 113 Hz to avoid the approximately 98 Hz third harmonic; identifiable-frequency control, not perfect-recovery promise |
| Walking C1/F1/Bb1/Eb2 over steady fan | 48 kHz mono; native event support and quiet capture; sustained notes never enter a noise-only label |
| Palm mutes, quiet decay, connected legato and saturation | 44.1 kHz stereo; define isolated-attack metric windows separately from connected events; saturation applied before final additive references |
| Missing C1 F0 harmonic proxy plus fan at theoretical F0 | 48 kHz mono; clean source is a linear sum of declared higher harmonics, no later nonlinearity; independent joint-fit absence check |
| Time-varying fan and declared shared gain envelope | 44.1 kHz stereo; save `Sbase,Nbase,a`; effective references `S=a*Sbase,N=a*Nbase,Y=S+N` are a synthetic gain model, not real AGC reconstruction |

The 32.000 Hz preservation sentinel is distinct from equal-tempered C1
`440*2**((24-69)/12)`. This tuning context is not real played-note truth.
Allow a fixture-global scale only before saving all components; never clip or
independently normalize `S`, `N` or `Y`. Define `Y` as the sum of the saved
component numeric references with explicit serialization rounding. Save float32
PCM but perform oracle calculations in float64 from those saved values; declared
float32 additivity tolerance is `2e-7` absolute full-scale units. Hash each byte
artifact, canonical metadata/config, generator and dependencies.

In the exact-collision case record `S'=S+u,N'=N-u` with same-frequency `u` and
verify both assignments give the same observation within serialization tolerance.
This is a non-identifiability witness, not a different label for worker training.
Missing-F0 check independently fits sine/cosine columns for F0 and every generated
harmonic plus intercept on a declared flat clean span of at least one second;
require fitted F0 amplitude `<=5e-5`, preserve harmonic amplitudes and reject a
poorly conditioned design (`condition_number>1e8`). No nonlinear shaping follows
this fixture's harmonic synthesis. A later measured output F0 is not automatically
regenerated musical F0 when the supplied fan already contains that frequency.

Inference input paths are opaque; arguments/manifests contain mixture/capture
identities and settings, never component paths, note/event truth or semantic case
names. Alias bytes must match the fixture mixture before inference. Evaluators
may read truth only after all outputs/masks are sealed; failed/absent outputs
retain explicit coverage/failure entries. Do not silently exclude hard cases.

## Frozen evaluation thresholds and applicability

These are predeclared engineering gates for the proposed first experiment, not
validated listening thresholds. Structural failures block a result; quality-gate
failures reject default adoption while preserving every measurement. Do not tune
thresholds on these fixtures or change a setting after seeing held-out results.

| Gate | Exact declaration |
| --- | --- |
| Native extent/identity | Same rate/channels/sample count; source/component/capture/config hashes match; no input overwrite |
| Bypass reconstruction | Float64 all-one-mask maximum absolute error `<=1e-10`; serialized float32 readback `<=2e-7` absolute error |
| Conditional additivity | Float64 `apply(S,M)+apply(N,M)` versus `apply(Y,M)` maximum absolute error `<=1e-10` when `Y=S+N` in memory; for independently float32-rounded Y use `<=4e-7` and report its input rounding residual separately |
| Known fundamental gain | Clean-only and identifiable oracle guitar: amplitude loss `<=0.5 dB`, boost `<=0.1 dB` on declared stable spans; test sentinel/C1 separately, all generated harmonics jointly |
| Attack energy/centroid | Isolated generator attack: oracle-guitar energy in first 20 ms loses `<=1 dB`, gains `<=0.5 dB`; squared-amplitude centroid shifts `<=2 ms`; native indices, no fitted time shift |
| Tail energy | Isolated generator tail 50–250 ms after onset: oracle-guitar RMS loss `<=1 dB`, boost `<=0.5 dB`; exclude overlapping connected events only by predeclared support, retain counts |
| Preattack leakage | In each isolated attack's preceding 100 ms, processed oracle-guitar RMS `<=-35 dB` relative to that source attack's first-20-ms RMS; label algorithmic pre-echo diagnostic |
| Broadband-noise improvement | `>=3 dB` reduction of oracle-noise integrated 140–8000 Hz power where declared nonzero/in-range; never require this target inside the protected low region |
| No-separation claim control | Exact cofrequency case must retain non-identifiable status; no simultaneous perfect-removal/preservation requirement and no real recovered-stem assertion |

Use known harmonic sine/cosine least-squares fits on native stable spans; report
sample count, elapsed duration, design conditioning, amplitude/phase errors and
exclusions. A fitting failure or a nonexistent source fundamental gives a null
amplitude-ratio metric, not a pass. A present fundamental with an output near
zero is a preservation failure, not missing-data censoring. Collision component
gains are evaluated on the frozen-mask oracle component, never projected from
the mixed output as if fan energy were absent.

Broadband power uses a declared full-support Hann FFT over the same evaluation
span before/after, with one-sided density normalization as above and band edges
reported. Preserve low-region noise residual, clean/music distortion, whole-mixture
power/coherence and counts as separate fields. Zero source components produce
null relative ratios with applicability `zero_reference`; zero output with a
nonzero reference is an explicit complete-attenuation result. Never add infinities
to JSON or average null/empty ratios into a favorable aggregate.

For the custom worker freeze `M(Y)` first, then evaluate `T_M(S)` and `T_M(N)`.
The conditional operator is linear for fixed M even though deriving M is not.
This accounts for the applied synthetic output; it does not prove an identifiable
mono decomposition or a real guitar stem. For black-box adaptive afftdn, separate
clean-only/noise-only/mixed-error experiments: `D(S+N)-D(N)` is an incremental
response, not `D(S)` or a recovered guitar output. If nonlinear dynamics were
added after masking, this linear component-accounting identity no longer applies.

Bound future workers to two numerical/FFmpeg threads and 120 seconds each,
serial within a declared 600-second comparison budget; fresh ignored directories,
no model/package downloads and no full-source processing here. Preserve timeout
and failure receipts. Native tests, synthetic quality, actual A/B/residue review,
master acceptance and AU/Logic delivery remain separate evidence classes.

## Primary implementation references and release evidence

[NumPy rFFT](https://numpy.org/doc/stable/reference/generated/numpy.fft.rfft.html)
and [inverse rFFT](https://numpy.org/doc/stable/reference/generated/numpy.fft.irfft.html)
define the transform normalization/real-input conventions. The explicit inverse
length avoids ambiguous reconstruction. [SciPy NOLA](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.check_NOLA.html)
documents the nonzero squared-window overlap denominator; verify it over actual
cropped native support rather than assuming an overlap percentage proves it.
These live reference pages do not alter the existing locked dependency versions.
[FFmpeg afftdn](https://ffmpeg.org/ffmpeg-filters.html#afftdn) remains a separate
black-box comparison; custom PSD-density units are not interchangeable with its
profile/floor knobs. Statistical-model limitations and speech/music mismatch
retain the primary citations in the frozen research receipt.

Before release, record appendix and canonical fixture-declaration hashes,
independent fixture audit findings, exact owned worker paths and the settings/
threshold receipt. Report observed tradeoffs without selecting a hidden best
case. The declaration alone establishes no candidate audio or preservation
acceptance. The concrete post-release synthetic evidence follows; existing
canonical DSP, default profiles and actual media remain unchanged.

## Post-release synthetic execution receipt

Root explicitly assigned only new
[`low_register_denoise_probe.py`](../../scripts/low_register_denoise_probe.py)
and [`test_low_register_denoise_probe.py`](../../tests/test_low_register_denoise_probe.py).
This unregistered worker uses the existing locked `.venv/bin/python` with
NumPy 2.5.3/SciPy; no install, catalogue/default/core-DSP change or actual audio
processing occurred. Ten waveform/metric tests passed in 1.304 s; system Python
skips these ten optional NumPy/SciPy tests rather than acquiring dependencies.
One early test assumption was corrected before execution: a 5 ms low-tone onset
shift need not move a truncated 20 ms energy centroid by more than 2 ms. A known
isolated pulse now tests centroid sensitivity; the declared musical metric and
threshold were unchanged. The centroid metric is not onset-accuracy proof.

The independent fixture owner froze the declaration before generation, then
generated and separately read back eight fixtures/64 seconds, 27 component WAVs,
native extent/finite/clip checks, capture clean-zero, conditional arithmetic,
exact-collision alternative assignment and missing-F0 joint fit. Declaration:
`artifacts/benchmarks/low-register-v1-declaration-20261006.json`, SHA256
`92ac90ba80dc0d815a064b2b1bf7f7825a6ff6ae936fe4630db0d5bd5ac521b0`.
The canonical separated fan is 113 Hz. The published calibration bank/pilot was
not changed. Exact amplitudes/envelopes remain in this fixture declaration.

| Executed artifact | SHA256 |
| --- | --- |
| Fixture index `low-register-v1-20261006/fixtures.json` | `03ebb568a4f473f12761dda7c771a7633e8b3e45285e6491fe10de74b787d014` |
| Discovery index `low-register-v1-20261006/discovery.json` | `c5b54bf0f412a18951f2ae903810d3dd0b0a6950bfb4e82e40950b9de415939c` |
| Worker revision | `384a99bca9e72212b5d9631e9b425424ea7b08fc41ce6eb4dde4d647b3ba3bc6` |
| Numeric test revision | `3a2b0a6f9941b42aecb9dbecd8c67c8de90e4011f055d48ff904821664a5e3f4` |
| All-masks seal `low-register-probe-20261006T0050/masks-sealed.json` | `ed69465c0d425afc15c18cb2faddc83fb3f9e3d5ad3432e19259ab6413a6048f` |
| Result `low-register-probe-20261006T0050/results.json` | `72bf702949e74641fe0d46b8badf0c2e6469567f385cefb8a3feb6aa0951255f` |

All artifact paths in the table are below `artifacts/benchmarks/`, except worker/
test source paths linked above. Execution command:

```sh
.venv/bin/python scripts/low_register_denoise_probe.py \
  --discovery-index artifacts/benchmarks/low-register-v1-20261006/discovery.json \
  --fixture-index artifacts/benchmarks/low-register-v1-20261006/fixtures.json \
  --output artifacts/benchmarks/low-register-probe-20261006T0050
```

Completed in 65.3489555 seconds, bounded to two numeric threads/120 seconds.
All 32 masks, outputs, residues and settings were saved/hash-bound before the
worker opened the fixture index or known component/truth files. Exact float64
same-mask additivity maximum was `1.6653345369377348e-16`; applying the same mask
to independently rounded stored mixture versus component sum differed at most
`8.319182093208255e-9`. Input/index hashes were unchanged. Zero hard failures;
two variant quality alerts, both the varying-fan/shared-gain fixture at noise
scale 0.5: 140–8000 Hz noise power fell 2.346 dB against the declared 3 dB gate.
Scale 1.0 fell 3.614 dB. The stationary fan-only case's broadband reduction was
3.170/5.165 dB at scales 0.5/1.0. These are known synthetic noise-component values,
not observed fan SNR in the phone take.

Readback independently rehashed 128 mask/density/processed/residue files,
checked all 32 nested discovery records against the seal and all 32 nested
evaluation records against the aggregate, and recomputed failure/alert counts.
Worker and published calibration-receipt hashes still match. Local Markdown
targets resolve and owned-file whitespace checks pass. No inference was rerun
for this readback.

Clean-only sentinel/C1 gain was 0 dB (its capture is silent). Tested stable
identifiable fundamentals lost less than 0.001 dB. This narrow result excludes
the exact collision and missing-F0 gain-ratio gates. The connected legato has no
single constant-frequency truth/fit; the palm-mute case contributes six isolated
attack/tail windows per variant, not a stable-F0 result. Temporal energy/centroid
metrics aggregate the two channels; they are not twelve independent per-channel
attack gates. Harmonic gain rows are per channel. Across the temporal windows:
attack loss at most 0.247 dB, absolute 20 ms energy-centroid change at most
0.122 ms, tail loss at most 0.285 dB, preattack RMS at most −38.827 dB relative
to attack RMS. They passed the recorded thresholds without time/gain fitting.

The exact-collision case remains explicitly non-identifiable. With a 0 dB low
floor its conditional guitar gain was approximately unity; with the 0.5 dB
floor it lost about 0.276–0.500 dB while low fan energy remained. This is not a
recovered stem or successful same-frequency separation. Tonal-only collision
noise has negligible numerical high-band reference energy; its large relative
high-band ratios are inapplicable to the broadband-noise gate and must not be
described as useful broadband reduction.

The missing-F0 fixture's processed oracle-guitar joint-fit F0 amplitudes were
`1.93e-7` through `4.97e-7` full-scale units versus approximately `8.97e-12` in
the source. These small residuals are diagnostics; the relative fundamental
gain is null for the absent source fundamental. The worker did not synthesize
an oscillator or infer notes. Existing fan energy at F0 prevents interpreting
the mixed output's F0 as recovered musical content. No new posthoc output-
absence threshold was selected to label these measurements a pass.

This first bank is a limited synthetic engineering comparison, not held-out
music acceptance. Preserve its exact metrics and exclusions; do not retune on
the observed varying-fan result. The next evidence is independent mask/metric
readback followed by root's bounded actual-comparison decision. No actual
candidate, listener preference, master acceptance or AU/Logic proof exists here.

Process receipt: actor audio_research | target owned new implementation appendix |
reason make frozen research implementable under explicit subsequent prototype
release | ruling R-HOOK-CONVERGENCE-20261004 / R-N13 | prior_state documented
separability design | result new unregistered offline worker/tests and bounded
source-known synthetic evidence; canonical DSP/profiles/actual media unchanged.
