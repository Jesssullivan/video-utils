# Independent low-register probe audit

Plan before independent audit. Authority: root's explicit synthetic-probe
audit assignment under the operator's restoration goal; repository AGENTS.md
and R-HOOK-CONVERGENCE-20261004 R-N12/R-N13. Owner `clip_baseline`. Own this
new receipt and, only where meaningful coverage is missing, new audit tests.
The frozen worker, fixture bank, source recording, current DSP/defaults and
saved probe artifacts remain read-only.

Audit frozen worker SHA-256
`384a99bca9e72212b5d9631e9b425424ea7b08fc41ce6eb4dde4d647b3ba3bc6`,
32 masks/results at `artifacts/benchmarks/low-register-probe-20261006T0050`,
results SHA-256 `72bf702949e74641fe0d46b8badf0c2e6469567f385cefb8a3feb6aa0951255f`,
and fixture index SHA-256
`03ebb568a4f473f12761dda7c771a7633e8b3e45285e6491fe10de74b787d014`.
Check mixture-only derivation and persisted sealing before oracle/index reads,
frozen controls and gain bounds, native overlap-add support, density units,
exact float64 identity versus rounded float32 mixture error, metric support
and alert denominators. Recompute saved-array metadata/hashes and selected
independent metrics without rerunning the full DSP bank. Report blocking
defects early; a passing synthetic audit does not adopt a default or accept
the actual take. Root owns any future actual-audio diagnostic release.

## Verdict

Positive independent audit of the frozen **synthetic** comparison; no must-fix
found. This is evidence about source control flow, stored numerical artifacts
and metric interpretation. It does not accept the actual recording, identify
real stems or adopt any processing default. Root separately controls release
of an actual-take diagnostic. No actual-take processing occurred in this audit.

## Independent checks

Read the complete frozen worker and its ten numerical tests. In `run()`, the
fixture index is initially converted to an absolute `Path`; that operation
does not read its contents. Phase one reads only discovery metadata and
hash-bound mixture audio, derives all four settings for all eight inputs,
saves 128 arrays and 32 discovery records, then writes/hash-binds
`masks-sealed.json`. The first fixture-index digest and JSON load occur after
that seal. Component/truth access occurs later. Evaluation loads the sealed
mask, checks its artifact hashes and applies that same mask to known
synthetic components. It does not derive a new mask from clean/fan truth.

Added [two independent tests](../../tests/test_low_register_probe_audit.py).
The orchestration test mocks only DSP/PCM decoding, intercepts the first
oracle-index access and independently checks the on-disk seal, all 32 unique
variants and all 128 array hashes. It stops before evaluation. It does not
claim to test native reconstruction, which has separate numerical tests.
The second test integrates PSD of combined DC/Nyquist content; it catches
incorrect one-sided doubling at either endpoint. Both pass in 0.512 seconds.
The existing ten numerical tests also pass in 1.573 seconds.

Read all saved arrays independently, without importing or running probe DSP:

- Exact hashes for 128 arrays match the seal. Every array is finite float64;
  all nested discovery records equal their sealed records, and nested
  evaluations equal aggregate results.
- Native processed/residue extent is `[8*sample_rate, channels]`. Saved mask
  frame/bin/channel dimensions and left/right padding match independent
  `L=8192`, `H=2048` arithmetic at native 44.1/48 kHz.
- Gain values span `0.3981071705534972..1`. Every saved gain respects its
  independently computed cosine floor: 0 or 0.5 dB ceiling through 80 Hz,
  transition through 140 Hz, and 8 dB broadband ceiling. This checks FFT
  coefficients; it is not a universal real-music preservation claim.
- `mixture - processed - residue` has maximum absolute error **0** in the
  saved float64 representation.
- Independently recomputed the initial 0.8-second capture PSD from the
  hash-bound mixture WAV using a periodic Hann, fully contained windows,
  one-sided endpoint weights and normalization `fs * sum(window²)`.
  Maximum absolute saved-density discrepancy is **1.3553e-20** in
  full-scale-squared/Hz. There are 14 complete capture frames at 44.1 kHz
  and 15 at 48 kHz; overlap means they are not independent averages.
- All worker/result/seal/index hashes still match at final readback.

The worker pads both edges by at least one full window, divides overlap-add
by the summed squared window, and crops to native samples. Existing bypass
tests cover low fundamentals, edge impulses, irregular lengths, mono/stereo
and a one-sample input. No shift fitting or loudness matching is used for
conditional component accounting.

## Accounting and metric coverage

Saved maxima, checked against the distinct predeclared limits:

| Quantity | Maximum absolute error | Limit |
| --- | ---: | ---: |
| Native float64 bypass | 1.6653e-16 | 1e-10 |
| Same-mask `D(S)+D(N)-D(S+N)` | 1.6653e-16 | 1e-10 |
| Serialized float32 input `S+N-Y` | 7.4506e-9 | 2e-7 |
| Same-mask components versus processed rounded `Y` | 8.3192e-9 | 4e-7 |

The exact float64 identity uses `S+N`, while the stored mixture is a rounded
float32 sum. The latter two rows are storage/accounting tolerances, not the
strict linearity tolerance and not denoising quality measurements. Same-mask
component outputs are conditional synthetic accounting, not recovered stems.

Coverage independently counted from evaluation records:

| Check | Applicable/measured denominator | Result |
| --- | --- | --- |
| Mathematical hard checks | 32 variants | 0 hard failures |
| Broadband noise reduction | 24 applicable variants | 2 quality alerts |
| Fundamental metadata flag | 20 variants | 4 have no stable F0 fit |
| Measured stable fundamental | 16 variants; 36 channel-event rows | −0.000993..+0.000104 dB |
| Palm-mute temporal checks | 4 variants; 24 stereo-aggregate attack windows | No alerts |

The six short palm-mute attacks and connected changing-pitch legato in
`lr06` do not have a one-second stable F0 fit after margins. Its four
`fundamental_gain_applicable=true` flags must not be presented as four
successful stable-F0 measurements. Exact collision and missing-fundamental
cases also do not establish recoverable fundamentals. Harmonic fits retain
per-channel rows and null values when source amplitude is below `5e-5`.

Temporal metrics sum channel energies before computing each attack centroid,
and RMS/mean-square quantities average across channels. These are **24
stereo-aggregate windows**, not 48 independent channel checks. Measured
attack-energy changes span −0.24664..−0.02145 dB; tail changes span
−0.28492..−0.00160 dB; centroid shifts span −0.05842..+0.12203 ms;
pre-attack RMS relative to attack RMS spans −50.4904..−38.8274 dB. They pass
the frozen thresholds only on these supported synthetic windows. Future
per-channel transient tests would add coverage rather than repair this
declared aggregate check.

The two genuine quality alerts are `lr08-p0-n0.5` and `lr08-p0.5-n0.5`:
known broadband-noise power changes are −2.3461052 and −2.3461056 dB,
respectively, against the declared reduction target of at least 3 dB.
The same changing-fan/shared-gain fixture at noise scale 1 gives −3.6144371
and −3.6144374 dB. Both 0.5-scale alerts remain visible despite zero hard
failures. No whole-bank "quality passed" claim is justified. The broadband
gate applies only where the generated source declares positive broadband
noise RMS; huge ratios of tiny out-of-band Hann leakage in a tonal-only
collision are descriptive, not broadband-cleanup failures. These source
labels are available only during evaluation.

This audit recomputed array hashes, dimensions, floors, density, residue and
coverage counts. Component-quality values above were read from verified
saved evaluations and audited against the implementation's formulas and
thresholds; the full same-mask component DSP was not rerun.

## Reproduction and frozen identities

Run the bounded independent control-flow/PSD tests and existing numerical
tests in the optional locked analysis environment:

```sh
.venv/bin/python -m unittest discover -s tests -p test_low_register_probe_audit.py -v
.venv/bin/python -m unittest discover -s tests -p test_low_register_denoise_probe.py -v
```

These tests use temporary synthetic data. The orchestration test deliberately
uses mocked one-sample arrays to isolate ordering; it is not a regeneration
of the 64-second bank or a source-audio render. Saved-artifact readback used
the native SciPy WAV decoder and NumPy with numerical threads capped at two.

| Frozen artifact | SHA-256 |
| --- | --- |
| Worker | `384a99bca9e72212b5d9631e9b425424ea7b08fc41ce6eb4dde4d647b3ba3bc6` |
| Results | `72bf702949e74641fe0d46b8badf0c2e6469567f385cefb8a3feb6aa0951255f` |
| Masks seal | `ed69465c0d425afc15c18cb2faddc83fb3f9e3d5ad3432e19259ab6413a6048f` |
| Fixture index | `03ebb568a4f473f12761dda7c771a7633e8b3e45285e6491fe10de74b787d014` |
| Discovery index | `c5b54bf0f412a18951f2ae903810d3dd0b0a6950bfb4e82e40950b9de415939c` |
| New audit tests | `ac5f46e43c0e133d9a226bf3ef74f5e23dc06460aa50b4caacae79e2b4ff654e` |

No frozen worker, fixture, saved probe output, actual media or existing
default was modified. Only this new receipt and the new independent test
file belong to this lane. Root/audio owner received the positive verdict
and the explicit two-alert/coverage limitations before any future diagnostic
release.
