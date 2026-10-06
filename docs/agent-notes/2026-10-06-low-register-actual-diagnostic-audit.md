# Independent actual low-register diagnostic audit

Plan before readback. Owner `clip_baseline`; root explicitly assigned saved-array
readback after its exact release in
`2026-10-06-root-low-register-diagnostic-release.json`, under repository
AGENTS.md and R-HOOK-CONVERGENCE-20261004 R-N13. Own this new receipt only.

Audit saved results SHA-256
`e946198d9a88c14045566d114a95deed75b9114afe01162723a517d825783e6b`
and sixteen arrays in
`artifacts/experiments/low-register-actual-diagnostic/run-20261006T0117`.
Check source/release/plan bindings, hashes, native extents, fixed gain floors,
frame clock/full-support flags and the conservative interior. Independently
recompute residue, RMS, band power and source-weighted coherence from saved
outputs and only the selected 20–30-second source/capture spans. No DSP rerun,
new decoding, full-take numeric reading, source edits, default adoption or
master/latest changes. Distinguish whole-interior periodogram power from the
203-frame Welch coherence estimator; neither is isolated music/fan truth.

## Verdict

Independent numerical readback **passes**, with no must-fix found. All sixteen
saved array hashes, four nested diagnostic records, source/release/plan/audit
bindings, native extents, gain floors and guarded mixture descriptors match.
This is a bounded actual-mixture diagnostic; no isolated fan/music gain or
real-note preservation has been measured, and no listening acceptance or
default adoption follows.

## Independent verification

Used the existing source WAV via a native read-only memory map. Only
`[882000,1323000)` (20–30 seconds, 441000 samples) and
`[180810,218295)` (4.10–4.95 seconds, 37485 samples) became numerical PCM
arrays. No original MOV decoding or full-take numerical pass occurred.
Original/decoded inputs and five protected latest/master artifacts were
stream-hashed as bytes before and after; all seven match the protected
receipts. Those byte hashes do not require numeric audio decoding.

The bounded readback recomputed these quantities directly, without importing
the processing worker or harness, deriving masks or applying DSP:

- All sixteen `.npy` hashes match saved jobs; values are finite float64.
  Four nested `diagnostic.json` records match aggregate results.
- Processed and residue arrays are `[441000,1]`; mask is `[221,1,4097]`;
  density is `[1,4097]`. Continuous independently calculated gain floors
  match the fixed 0/0.5 dB low and 8 dB broadband settings, with no gain
  above one.
- Source-global `H=2048` frame alignment uses the synthetic 1360-sample
  prefix (`882000 mod 2048`). All 221 starts and centers match independent
  arithmetic; 211 windows have full original excerpt support. Artificial
  edge context remains excluded from descriptive metrics.
- Conservative metrics use source samples `[890191,1314809)`: 424618
  samples after dropping `8191=L−1` samples at each excerpt edge. All windows
  contributing to those samples have complete original excerpt support.
- Welch coherence uses 203 periodic-Hann windows of 8192 samples on the
  original global grid. First start is 890880; final start is 1304576.
  Band selections contain 5 bins (20–45), 14 bins (45–120), and 1460 bins
  (140–8000). These overlapping windows are not 203 independent estimates.
- Independently recomputed capture PSD from the previously selected
  0.85-second span, trimming its start to global sample 182272. Fit support
  is 36023 samples; 14 complete periodic-Hann windows contribute. Capture
  contamination is unresolved; this is not a verified fan-only measurement.
- `source - processed - residue` has maximum absolute error **0**.
  Maximum capture-density discrepancy is **4.2352e-22** in
  full-scale-squared/Hz. Independently recomputed band-change discrepancy is
  at most **3.7193e-15 dB**; coherence discrepancy is at most **6.6613e-16**;
  RMS change matches exactly in this calculation.

The independent calculation took 32.575 seconds with numerical threads
capped at two, including protected-file hashing. It did not repeat inference
or generate audio. The initial receipt-envelope comparison was corrected to
compare `protected` maps: the before receipt carries `latest_run_dir`, while
the after receipt carries `all_unchanged`. That metadata assertion occurred
before any numerical source access; it was not an input/artifact discrepancy.

## Recomputed mixture descriptors

Power changes below use a **single periodic-Hann periodogram over the entire
guarded 424618-sample interior**, with one-sided endpoint weights and
full-scale-squared/Hz normalization. Source-weighted magnitude-squared
coherence uses the separate 203-window Welch estimator. The saved adjacent
Welch frame/bin metadata describes coherence, not the power-change estimator.
Neither estimator isolates the guitar or fan. No fitted alignment shift,
normalization, EQ or compression is involved.

| Low ceiling / noise scale | 20–45 Hz power dB | 45–120 Hz power dB | 140–8000 Hz power dB | Mixture RMS dB | Residue RMS |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 / 0.5 | −0.0000248915 | −0.049019 | −0.219238 | −0.186818 | 0.00408050 |
| 0 / 1 | −0.0000406568 | −0.092227 | −0.391856 | −0.333510 | 0.00653696 |
| 0.5 / 0.5 | −0.395073 | −0.075656 | −0.219238 | −0.189924 | 0.00408946 |
| 0.5 / 1 | −0.467096 | −0.133071 | −0.391856 | −0.338373 | 0.00654774 |

| Low ceiling / noise scale | 20–45 Hz coherence | 45–120 Hz coherence | 140–8000 Hz coherence |
| --- | ---: | ---: | ---: |
| 0 / 0.5 | 0.9999999963 | 0.9999579150 | 0.9979492776 |
| 0 / 1 | 0.9999999906 | 0.9998749437 | 0.9950253679 |
| 0.5 / 0.5 | 0.9998989579 | 0.9999377781 | 0.9979492776 |
| 0.5 / 1 | 0.9999743558 | 0.9998376976 | 0.9950253678 |

The 0 dB low ceiling leaves aggregate 20–45 Hz mixture power effectively
unchanged on this supported interval. The 0.5 dB ceiling permits about
0.40–0.47 dB less power there. These are mixture changes, not verified C1
gain or fan reduction. High coherence describes similarity of mixtures; it
does not show absence of guitar loss, separate sources, identify notes or
establish good tone. The 140–8000 Hz mixture reduction cannot be substituted
for the synthetic known-noise reduction target. The prior synthetic bank's
two quality alerts remain relevant and have not been cancelled by this run.

Every saved band retains `musical_component_gain=null` and
`isolated_fan_reduction=null`. All jobs retain
`noise_only_capture_verified=false`, `listening_accepted=false` and
`default_adoption=false`; aggregate `isolated_sources_identified`,
`master_replaced` and `media_exported` are also false. No actual quality-pass
or recovered-guitar claim is present.

## Hash-bound evidence

| Artifact | SHA-256 |
| --- | --- |
| Actual results | `e946198d9a88c14045566d114a95deed75b9114afe01162723a517d825783e6b` |
| Preregistered v2 plan | `ed664a3898ec1e25103fa9062567078cbc2326d4fa01346d9b45565ebda46b75` |
| Root release | `26bb0a5cc3a1d72e95471830f72ceeb706e5aed21c3474dc48c838e0e2a8225b` |
| Positive synthetic audit | `48a47efe16a291c6afa497d55a0653b0f0f7c8ff80e2aa109b030dd0e6dea7cb` |
| Frozen harness | `2b84f9f7f7b49b691cec68b83546fbf378fa172296e6339aa03c5552fc42c284` |
| Frozen worker | `384a99bca9e72212b5d9631e9b425424ea7b08fc41ce6eb4dde4d647b3ba3bc6` |
| Original MOV | `a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6` |
| Existing decoded WAV | `d68e49688293b1fb8c7c2566e2ecd6e31df9972af013dd23454e15864654bd2a` |

Only this new receipt was written by the audit lane. All frozen results,
arrays, source media, masters and latest pointer remain unchanged. Root and
audio owner received the positive readback and estimator/claim boundaries.
