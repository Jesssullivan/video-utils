# S2 lane `lowreg_spec_v4`: low-register spectrogram render spec (xoruby V4)

Sprint `20261006-s2`, Linear TIN-5608 (parent TIN-5599, related TIN-5546,
peer request V4 recorded under TIN-5186). Branch
`sprint/20261006-s2/lowreg_spec_v4`; worktree
`.local/sprint2/lowreg_spec_v4`. Root integrates and signs; this lane never
pushes, merges, writes Linear or touches other worktrees. Authority: S2 manifest
`program/sprints/20261006-s2.json`, repository `AGENTS.md`,
R-HOOK-CONVERGENCE-20261004 (R-N11/R-N12/R-N13).

Phase 1 (this document) freezes the contract **before any numerics**. No
fixture, matrix, golden or real-take render has been computed for this lane.

## Why this lane exists

The xoruby peer adopted V4 "with log-mel baseline, PCEN experimental, separate
attack branch" once a path and sha256 merge. The sting inference lane reports a
Rune 6r PCEN render that dropped everything below 400 Hz, a suspected cause of
chance-level scores. The xoxd 2021 reconstruction also starts at 400 Hz, and
even xoxd's default (16 kHz, 400-sample window, 512 FFT, 31.25 Hz bins, first
HTK band near 64 Hz) cannot represent the 32.703 Hz C1 string
([`XOD_SPECTROGRAM.md`](../../research/XOD_SPECTROGRAM.md)). V4 is a separate,
low-register-only feature branch with a frozen numeric definition and a golden
file another implementation can match. It is a feature transform: it restores
no audio, separates no stem and identifies no note.

## Scope

In scope: a frozen render specification, its machine-readable form with a
self-hash, a deterministic stdlib-first reference implementation (numpy
optional with the same result), a deterministic generated fixture, a <= 50 KB
golden file, tests, and a peer note.

Out of scope: any default/detector/profile/master change; the short-window
attack/onset branch (stays the existing log-mel rhythm frontend); PCEN knob
tuning; pitch, tonic, note or mistake claims; catalog/MCP tool admission;
rendering or modifying the original take, the accepted FULLER run
`artifacts/runs/20261006T041633Z-990aa1bd6737`, or Desktop/Documents media;
model downloads; sending any real-take-derived data to peers.

## Owned files

| Path | Role |
|---|---|
| `docs/spec/sprints/LOWREG_SPEC_S2.md` | This lane contract |
| `docs/spec/LOW_REGISTER_SPECTROGRAM_SPEC.md` | Human render spec (normative prose) |
| `program/spectrogram-lowreg-v1.json` | Machine spec, `version` + `spec_sha256` |
| `scripts/lowreg_spectrogram.py` | Reference implementation + fixture + golden CLI |
| `tests/test_lowreg_spectrogram.py` | Golden, parity, geometry, refusal tests |
| `tests/fixtures/lowreg-golden-v1.json` | Golden values (<= 50,000 bytes) |
| `docs/agent-notes/peers/xoruby/V4-render-spec.md` | Peer summary with paths and sha256 |
| `docs/agent-notes/sprints/20261006-s2/lowreg_spec_v4-*.json` | Lane receipts |

Scratch/real outputs: `artifacts/s2/lowreg_spec_v4/` (gitignored), never
`artifacts/runs/*`. Root-owned files changed: **none requested**. The module is
an experimental research helper, not an advertised tool; MCP/skill admission
is a later root decision and is not requested in S2.

## Frozen render definition (v1)

All arithmetic is IEEE-754 float64. Normative prose goes in
`LOW_REGISTER_SPECTROGRAM_SPEC.md`; these values are the contract it must state.

| Item | Value |
|---|---|
| Analysis rate | 8000 Hz, mono. Multi-channel input: arithmetic mean of channels in float64 |
| Input decode | PCM16 WAV, `int16 / 32768.0`. No DC removal, pre-emphasis, high-pass, notch or dither |
| Other rates | Refused by the v1 reference (exit 2). An explicit external resample is a caller pre-stage whose command, tool version and output sha256 are recorded; its group delay is `null` (unmeasured) |
| Window | Periodic Hann, length 4096: `w[n] = 0.5 - 0.5*cos(2*pi*n/4096)` |
| n_fft | 4096 (512 ms support), one-sided bins j = 0..2048, spacing 8000/4096 = 1.953125 Hz |
| Hop | 160 samples = 20 ms |
| Framing | No centre padding. Frame t uses samples [160t, 160t+4096); `n_frames = 1 + floor((N-4096)/160)`; N < 4096 refused |
| Time axis | Frame centre `(160t + 2048)/8000` s from the first analysed sample; first centre 0.256 s. Head [0, 0.256) s and the tail after the last centre are reported as partial-support coverage, not dropped silently |
| Spectrum policy | **Power**: `P[t,j] = |X[t,j]|^2 / S^2`, `S = 2048.0` (analytic periodic-Hann sum). No one-sided x2 factor. Values are window-normalized power samples, not calibrated dBFS or SPL |
| Magnitude policy | Not part of v1. The filterbank is applied to power; `sqrt` of band power is **not** a magnitude filterbank and must not be labelled one. A magnitude variant needs a new version |
| Log bins | `f_k = 20 * 2^(k/24)` Hz, k = 0..159 (K = floor(24*log2(2000/20)) + 1 = 160; last centre 1974.03 Hz <= fmax 2000) |
| Filter shape | Triangle in Hz at each FFT bin frequency `f_j = 1.953125 j`: left half-width `L_k = max(f_k - f_k*2^(-1/24), 1.953125)`, right `R_k = max(f_k*2^(1/24) - f_k, 1.953125)`; weight `max(0, 1 - |f_j - f_k| / (L_k or R_k))`; normalized to unit sum per filter |
| Band energy | `E[t,k] = sum_j W[k,j] * P[t,j]` |
| Log output | `D[t,k] = 10*log10(max(E[t,k], 1e-10))` (absolute floor, not max-relative) |
| PCEN input | `Z = E * 2^31` (xoxd power-scale convention; explicit, not inherited) |
| PCEN params | gain 0.98, bias 2, power 0.5, time constant 0.4 s, eps 1e-6 |
| PCEN smoother | `T = 0.4*8000/160 = 20` frames; `b = (sqrt(1+4T^2) - 1)/(2T^2)` (~0.0487656); `M[0] = Z[0]`; `M[t] = (1-b) M[t-1] + b Z[t]` |
| PCEN output | `PCEN[t,k] = (Z[t,k] / (eps + M[t,k])^gain + bias)^power - bias^power` |
| PCEN state | Causal; the smoother row M is carried across frames and across streamed blocks; block processing must equal batch exactly. No reset on block boundaries |

Consequences that the spec and every output must state, not hide:

1. Below about 66.7 Hz (right side) / 68.6 Hz (left side) the 24-per-octave
   spacing is narrower than the 1.953 Hz FFT spacing, so each low filter
   degenerates to linear interpolation between adjacent FFT bins. Adjacent low
   bins are **not independent measurements**.
2. The Hann main lobe spans +/-3.9 Hz (two FFT bins) while a semitone at C1 is
   about 1.94 Hz. Therefore `pitch_resolution_claim: "none"`. Seeing energy near
   32.7 Hz is not C1 identification; a dominant peak is not a played note.
3. A 512 ms support contains ~16.7 C1 cycles but blurs a 178 BPM sixteenth
   (~84.27 ms) across ~6 subdivisions. The 20 ms hop samples a 512 ms-smoothed
   trajectory; it is not 20 ms time resolution. **The short-window attack branch
   stays separate** and remains the source of onset/timing evidence.
4. Log-power (`D`) is the baseline representation of this branch, and log-mel
   remains video-utils' baseline frontend overall. PCEN is **experimental**:
   prior fixed-knob work found default PCEN weaker than log-mel on several
   onset-invariance cases and better on others
   ([PCEN ablation](../../agent-notes/2026-10-05-pcen-frontend-ablation.md)).
   v1 fixes the knobs for reproducibility, not because they are recommended.

## Deterministic fixture (sealed before numerics)

Generated with Python stdlib only (integers and `math.sin`); numpy is never used
to build it.

- Rate 8000 Hz, mono, N = 19200 samples (2.4 s).
- Steady broadband: `b[n] = 0.02 * (2u_n - 1)`, `u_n = (z_n >> 11) * 2^-53`,
  `z_n` = SplitMix64 outputs, seed 20261006 (decimal), one draw per sample.
- Harmonic tone: `f0 = 440*2^((24-69)/12)` = 32.70319566257483 Hz (C1 per
  `program/instrument.json`; equal-temperament theory, not a measurement).
  `h[n] = e[n] * sum_{m=1..6} a_m sin(2*pi*m*f0*n/8000)`,
  `a = [0.30, 0.15, 0.10, 0.06, 0.04, 0.03]`, zero phase.
- Envelope: `e = 0` for n < 4800 (0.6 s), `(n-4800)/80` for 4800 <= n < 4880
  (10 ms linear attack), 1 afterwards. This exercises PCEN state adaptation and
  makes the 512 ms onset blur visible in the golden.
- `x = h + b`; PCM16 encode `clamp(round(x*32768), -32768, 32767)` with Python
  `round` (half-even); expected clipped samples 0 (|x| <= 0.70).
- Written with stdlib `wave` as a 44-byte-header RIFF PCM16 mono file. The
  golden records `wav_sha256` (file bytes) and `pcm_sha256` (data chunk), so a
  libm last-ulp difference in `math.sin` is absorbed by quantization and any
  real divergence is caught by hash, not by tolerance.
- Expected geometry: 95 frames x 160 bins per matrix (15,200 cells; 30,400 for
  D and PCEN together).

## Golden file (`tests/fixtures/lowreg-golden-v1.json`, <= 50,000 bytes)

Fields: `schema` `lowreg-golden-v1`; `spec_version`; `spec_sha256`; fixture
parameters, `wav_sha256`, `pcm_sha256`, `n_samples`; `shape`; `backend` that
produced it (`stdlib`); `tolerance {abs: 1e-9, rel: 1e-9}` applied as
`math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)`; generator script sha256 as
provenance only (not a test gate). Stored values, both D and PCEN, as Python
`repr` floats:

- Full rows for frames {0 (pre-onset, steady broadband), 17 (centre ~0.596 s,
  inside onset blur), 94 (last, sustained)}: 3 x 160 x 2 = 960 values.
- Full trajectories for bins {0 (20.00 Hz, sub-fundamental), 17 (32.68 Hz,
  nearest f0), 28 (44.90 Hz, between harmonics 1 and 2), 41 (65.36 Hz, nearest
  2 f0), 150 (1522.19 Hz, broadband only)}: 5 x 95 x 2 = 950 values.
- Full-matrix aggregates per matrix: sum, min, max (6 values), plus frame-centre
  seconds and bin-centre Hz for the stored indices.

Total stored values 1,910 + 6 aggregates. If serialization exceeds 50,000
bytes, reduce in this fixed order without touching tolerance: drop bin 150
trajectory, then frame 17 row; record the reduction in the golden. The golden
is written only by an explicit `golden --write` command and only for a new spec
version; tests never write it.

## Reference implementation interface (`scripts/lowreg_spectrogram.py`)

- `fixture --out PATH.wav` writes the fixture (refuses existing paths).
- `render --wav PATH --out-dir DIR` writes `render.json` plus row-major
  float64 little-endian `log_power_db.f64le` and `pcen.f64le`, each with sha256
  in `render.json`; refuses existing output files, non-8000 Hz, non-PCM16,
  fewer than 4096 samples, symlinked input or output escape.
- `golden --check|--write PATH`; `spec --sha` prints the recomputed spec hash.
- Backend: `stdlib` (reuses `scripts/guitar_features.fft`, radix-2) by default;
  `numpy` (`numpy.fft.rfft`, same formulas and order) when importable and
  requested. Both must match the golden within tolerance.
- Streaming API: `PcenState` carrying the M row and frame count;
  `process(block)` returns frames for that block.
- Never mutates the input; re-hashes it after render.

### Required output fields, including explicit unknowns

`render.json` and the golden carry these exactly; a null always has a reason.

| Field | Value |
|---|---|
| `spec_version` / `spec_sha256` | `lowreg-spectrogram-v1` / hash of machine spec |
| `input.sha256`, `sample_rate`, `channels`, `downmix` | measured; signal version consumed |
| `pitch_resolution_claim` | `"none"` |
| `note_identity`, `intended_note_reference`, `tonic`, `mode` | `null` (no approved reference; spectral peaks are not notes) |
| `onset_timing` | `null`, reason: use the separate short-window attack branch |
| `temporal_support_seconds` / `hop_seconds` | 0.512 / 0.02 with the sixteenth-blur caveat |
| `interpolated_below_hz` | {left: ~68.61, right: ~66.65} |
| `coverage` | head/tail partial-support seconds |
| `resampler`, `resampler_group_delay_samples` | `null` when input is native 8000 Hz; otherwise caller-supplied record and `null` delay (unmeasured) |
| `calibration` | `uncalibrated_digital_scale`; microphone response `unknown` |
| `denoise_or_profile_applied` | `unknown` unless the caller binds the input to a run manifest |
| `pcen_status` | `experimental_fixed_knobs_not_tuned`; `baseline: log-power (log-mel remains project baseline)` |
| `listening_acceptance` | `not_assessed` |
| `adoption` | `none` (no default, detector, profile or master change) |

## Completion metrics (denominators and claim classes)

Claim classes: **M** = measurement on generated/deterministic data;
**C** = construction-truth sanity on the generated fixture (not real-guitar
evidence); **I** = inference; **L** = listening. This lane makes no I or L
claims; real-take evidence is `not_run`.

| ID | Class | Metric | Pass |
|---|---|---|---|
| M1 | M | Golden regeneration: stored values within tolerance / stored values | 1910/1910 (or reduced count recorded), aggregates 6/6, shape 2/2 |
| M2 | M | Fixture identity: `wav_sha256` and `pcm_sha256` match | 2/2 |
| M3 | M | Spec identity: recomputed `spec_sha256` equals machine spec and golden | 2/2 |
| M4 | M | stdlib vs numpy full-matrix cells within tolerance | 30,400/30,400, or `not_run` when numpy is unavailable (never counted as pass) |
| M5 | M | PCEN streamed vs batch, block sizes {1, 7, 95}: exactly equal cells | 15,200/15,200 per block size |
| M6 | M | Geometry: non-empty filters, unit sum within 1e-12, centre formula | 160/160 each; 95 frames; first centre 0.256 s |
| M7 | C | Low register retained (no 400 Hz or 80 Hz floor): `D[94,17] - D[0,17]` | >= 20 dB (prediction stated before numerics) |
| M8 | C | Steady-tone separation: `D[94,17] - D[94,28]` | >= 10 dB; explicitly not a pitch or note claim |
| M9 | M | Refusals: wrong rate, non-PCM16, < 4096 samples, existing output, symlink input, non-finite array via API, spec-hash mismatch | 7/7 refused with unchanged inputs |
| M10 | M | Golden size | <= 50,000 bytes |
| M11 | M | Input invariance: fixture WAV sha256 before/after render | 1/1 unchanged |
| M12 | M | Runtime: stdlib test module wall time on neo | recorded; budget <= 120 s |
| M13 | doc | V4 note states spec path+sha256, golden path+sha256, log-mel baseline, PCEN experimental, separate attack branch, `pitch_resolution_claim: none` | 6/6 statements |

A failed C gate is reported as a finding (the prediction was wrong), never
fixed by changing the fixture or knobs after seeing values.

## Test protocol

From the worktree root, owned module only:

```
PYTHONPATH=tests python3 -m unittest test_lowreg_spectrogram -v
PYTHONPATH=tests /Users/jess/git/video-utils/.venv/bin/python -m unittest test_lowreg_spectrogram -v
```

The first (system Python 3.12, no numpy) runs stdlib tests; the numpy parity
class is skipped with reason `numpy not importable` and M4 is recorded
`not_run` for that interpreter. The second uses the existing locked analysis
environment (numpy 2.5.3, read-only, nothing installed) for M4. Directly
affected module: `test_guitar_features` (the reused FFT), run once with system
`python3`. No FFmpeg, no real media, no full suite. Test classes:
`SpecTests` (M3, M6), `FixtureTests` (M2, M11), `GoldenTests` (M1, M7, M8,
M10), `StreamingTests` (M5), `RefusalTests` (M9), `NumpyParityTests` (M4).
Temporary files use `tempfile` and are deleted; receipts record exit code,
test counts, skips and wall time in
`docs/agent-notes/sprints/20261006-s2/lowreg_spec_v4-tests.json`.

## Preregistration

No comparative experiment is run: there are no arms, no scored truth, no
held-out data and no tuning. The fixture, seed, stored indices, tolerance and
C-gate predictions above are sealed in this commit before any value is
computed; they may change only through a new spec version. Optional stretch
(not part of done): one private render of the accepted FULLER audio after an
explicit FFmpeg 8 kHz pre-stage, written only under
`artifacts/s2/lowreg_spec_v4/`, hash-bound, n = 1, descriptive only; nothing
derived from the real take is shared with peers (V6 privacy wording is held for
operator approval).

## Phases

1. Contract freeze (this commit; no numerics).
2. Implement spec doc, machine spec, reference script, tests; generate golden
   once; commit owned files.
3. Run the test protocol, write the tests receipt and V4 peer note with final
   hashes; hand to root for audit, signed merge and the TIN-5186 post.
