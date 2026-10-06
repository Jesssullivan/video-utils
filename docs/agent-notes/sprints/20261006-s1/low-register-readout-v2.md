# S1 low-register owner readout

Authority: operator's five-hour S1 sprint; R-HOOK-CONVERGENCE-20261004,
R-N11/R-N12/R-N13. Independent arithmetic review passed all36rows/348files and24harmonic channel-event fits/25files; all checked bytes remained unchanged.
Exact helper0fe36986320083506ec6629328bf2ac20cd55bd20d2474bf550977b27a2ca94d,
plan d1a85f0248be3d224ed3b301c91016c2f61081b0589789c6faf556a561e52cf8,
result56a8440a1d812fbab25f36d8a6c88a905365828402ac07b1c43101d126fa1e33.

One released numerical run finished terminal0 in45.324seconds. Nine generated
cases, four frozen arms,36rows and72unique source seconds were evaluated. Native
44100/48000Hz mono/stereo insertion calibration measured1102/1200samples in all
four controls. Zero clipped output sample-values out of17,558,400 overall.
Raw auditable artifacts total793,862,454bytes under768MiB. Original recording,
accepted fullquality master and Desktop sharing export were never processed.

| Measurement | captured NR8 | captured NR10 | protected fixed mask |
| --- | --- | --- | --- |
| Eligible fundamental channel-events |9|9|9|
| Fitted fundamental response range dB |−0.06927..+0.00213|−0.06939..+0.00242|−0.00036..+0.00010|
| Broadband noise-control attenuation range dB |1.146..7.407|1.198..8.876|3.614..5.416|
| ≥3dB broadband noise control cases |6/7|6/7|7/7|
| Palm attacks/post-onset-energy gates |6/6|6/6|6/6|
| Connected legato sustain change dB |−0.12634|−0.12321|−0.00626|
| Rows with any predeclared gate alert |1/9|1/9|0/9|

The one NR8/NR10 alert is the saturated walking fixture: a175Hz tonal fan remains
inside the140–8000Hz band, giving only1.15/1.20dB aggregate noise-control reduction.
NR10 modestly improves noise-control attenuation on these cases, while its
nonlinear interaction and palm-mute energy changes grow slightly. No comparison
with a gain-normalized or compressed final master was made.

The fixed-mask arm preserves low frequencies by imposing unity gain below80Hz.
Consequently it retains the colliding C1 fan line too:20–45Hz noise change is
approximately0dB in exact/near collision, palm-legato and missing-F0 cases.
A0/9 alert result therefore does not mean successful fan separation or a better
real-take master. The preservation/noise tradeoff is deliberate and remains
experimental; no default is adopted.

Afftdn metrics describe D(g+n)−D(n) with an identical noise capture and separate
D(g) control. Its residual D(g+n)−D(g)−D(n) is nonzero, approximately−22..−27dB
relative guitar energy in the collision/palm examples. These are nonlinear
counterfactual responses, not isolated guitar or mixture residual-noise stems.
Only bypass and the mixture-estimated fixed mask support conditional known
component accounting. Exact and0.75Hz near collisions are excluded from unique
separation/fundamental-gain grading; missing-F0 and guitar-absent controls are
also excluded. Each arm has6palm events,1legato span,7broadband-noise cases and
9eligible fundamental channel-events; all raw fits and excluded cases remain.

Missing-F0 counterfactual20–45Hz ratios of+27dB compare against tiny source
leakage, and exact-collision140–8000Hz noise-control ratios of+82dB compare
against tiny tonal leakage. They are unsupported as fundamental-recovery or
broadband-noise claims. Their raw joint-fit amplitudes remain in the receipt;
no recovered fundamental or missing-note correctness is asserted.

Before execution the independent audit found zero-output preservation rows
were falling out of denominators. The corrected source includes complete
attenuation in the denominator and flags fundamental/attack/tail/legato loss;
an independent synthetic zero-response test reproduces this behavior. Active
energy uses the union of declared event spans, with a separate frame denominator.

Independent missing-F0 joint fits reproduce source amplitude8.97e−12 and
counterfactual output amplitudes0.006014(NR8)/0.006326(NR10), compared with
2.82e−7 under the conditional mask. These are source-null nonlinear responses;
never recovered guitar fundamentals. The zero-alert gate count does not test
fundamental invention on this excluded control. Follow-up should explicitly
quantify source-null response alongside preservation, without adopting a default.
