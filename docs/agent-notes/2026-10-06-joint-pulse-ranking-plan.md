# Preregistered isolated joint pulse/phase/subdivision ranking

Owner `/root/meter_inference`; authority: root's explicit read-only research
assignment under the operator's active ten-hour parallel goal, repository
AGENTS.md and R-N13. Registered before reading actual features for this new
experiment. Earlier pulse observations are development context, not withheld
data. Canonical rhythm, meter, phrase, registry and defaults are frozen.

Use only the existing stronger run's cached `analysis.json`, source hash and
manifest. No waveform decoding or STFT. Freeze twelve variants: observed fitted
pulse ×0.5/1, subdivisions1/2/3, and spectral-flux/SuperFlux event proxies.
Estimate each physical event-grid phase by a fixed64-bin circular search using
event timestamps, then refine using the median wrapped residual. The operator's
approximately178 BPM is not an input to phase fitting or candidate generation;
compare it descriptively only after durable predictions exist.

Alignment tolerance is fixed15ms (three existing5ms analysis hops), with no
click-mask assumption. Score support above the random-phase opportunity
`2*tolerance/grid_interval`, then multiply by occupied-grid-slot fraction.
Local support is measured in fixed8second windows. Gates: ≥12events,
overall alignment≥0.65, occupied slots≥0.50, at least three populated local
windows, and ≥80% of populated windows with support≥0.65. An insufficient or
inconsistent candidate stays unknown. Dense grids receive the opportunity
correction; smaller residual alone never wins. Spectral events remain mixture
attacks with unknown identity and detector delay.

Joint pulse selection requires both proxies to support the same physical grid,
each passing those gates, within5ms of fitted phase modulo interval. Distinct
supported physical-grid families need a score margin≥0.10. A grid that can be
represented at both pulse aliases (e.g.178/1 and89/2) does not identify the
metrical pulse; return pulse unknown. Meter, intended subdivision, note identity
and mistake grading remain null, including when a physical grid is repeatable.
Existing MFCC0 accent-cycle ranks are descriptive, never a tie-breaking score.

Before actual inference, run deterministic event-only controls: uniformly
spaced delayed events should admit their physical grid while preserving alias
ambiguity; alternating duplet/triplet texture with neither stable across windows
must reject a single global subdivision; irregular jitter must abstain. Controls
are algorithm checks rather than audio or musician accuracy. Freeze settings and
harness hashes before invoking actual inference. No retuning after results.

Bounds: twelve actual cached variants,≤20000events per proxy,≤36001feature
frames,≤1800seconds existing extent; stdlib only, two numerical thread variables,
parent120second timeout. Save predictions before prior comparison, record input
hashes before/after and preserve all rejected candidates. Artifacts go only to a
new `artifacts/experiments/meter-pulse/joint-*` directory.

Research basis: [FMP local-pulse hierarchy](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C6/C6S3_PredominantLocalPulse.html)
separates observable pulse from metrical level; [joint rhythmic-pattern
modeling](https://www.cp.jku.at/research/papers/Krebs_etal_ISMIR_2013.pdf)
motivates combined tempo/pattern observations while lacking deathcore-specific
validation. This heuristic experiment ships neither a trained meter model nor
confidence probabilities.
