# S1 low-register comparison protocol

This experimental helper compares nine generated known-component cases, never
real-recording stems. It is not an admitted product tool and has no default
adoption authority. Original/master/Desktop media are not inputs or outputs.

The frozen arms are bypass, captured FFmpeg afftdn NR8 and NR10, and one existing
protected-mask arm (0 dB low ceiling, 8 dB broadband ceiling, density scale1).
Afftdn controls reuse accepted capture *settings* nf−40, ad0, gs0, tn0 with a
fixture's own noise-only first0.8seconds. They do not reuse the real fan spectrum,
apply EQ/compression/loudness or stand in for the accepted mastered delivery.
All masks and mixture renders are sealed before component evaluation.

Fixtures reuse the eight source-known low_register_fixtures cases plus a near
collision line0.75Hz above C1. Controls cover32Hz/C1, absent fundamental, exact
and near fan collisions, palm attacks, connected legato, saturation, varying fan
and shared capture gain. Native44100/48000Hz and mono/stereo extents remain fixed.
Each case is8seconds; nine cases supply72unique source seconds. Four arms yield36
rows. RNG seeds and signal parameters are frozen before numerical execution.

Afftdn is nonlinear. Separately processing clean and noise does not reveal its
components in a mixture. Use identical captured noise and derive the *paired
counterfactual guitar response* D(g+n)−D(n), the clean-only control D(g), and the
interaction residual D(g+n)−D(g)−D(n). These are diagnostic comparisons, never
recovered or uniquely attributable stems. Exact collision is nonidentifiable;
near collision is particularly sensitive and does not establish separation.
The frozen-mask arm applies one mixture-estimated mask separately to known g/n
and permits conditional component accounting with an explicit additivity check.

Report native full/active guitar energy,20–45Hz change, jointly fitted harmonic
amplitudes, first20ms attack energy/centroid,50–250ms post-onset energy, connected
legato sustain energy, noise-control energy/bands, interaction residual, mixture
error and clipping. Every null has a reason and denominator. Missing-F0 fit is
reported as output amplitude, never fundamental recovery. Noise-control results
for afftdn are not residual-noise estimates inside the processed mixture.

Preservation gates are predeclared: fundamental −0.5..+0.1dB when supported,
attack/tail/legato −1..+0.5dB, absolute attack centroid shift≤2ms. Noise-only
broadband gate is≥3dB attenuation when broadband noise exists. A zero-noise or
zero-guitar reference excludes that ratio; missing-F0 excludes fundamental-gain
ratio; exact/near collision excludes identifiable separation claims. Negative
tradeoffs remain results. No quality failure causes arm retuning or adoption.

Execution bounds: one process, two numerical threads,≤54eight-second FFmpeg
passes plus≤4latency calibration passes,180second overall monotonic deadline,
20seconds per subprocess bounded by remaining deadline,≤768MiB saved audio per
run, fresh artifact-only output. The preregistered plan includes source hashes,
case declaration, settings, metric gates and deadline; a changed plan/helper or
reused destination is refused. Failure retains a receipt rather than publishing
a success. Root authorizes capacity before numerical execution.
