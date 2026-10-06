# Low-register spectrogram render specification v1 (`lowreg-spectrogram-v1`)

Normative prose for the xoruby V4 low-register feature branch. Sprint
`20261006-s2`, lane `lowreg_spec_v4`, Linear TIN-5608. Contract:
[`sprints/LOWREG_SPEC_S2.md`](sprints/LOWREG_SPEC_S2.md). Machine-readable form:
[`program/spectrogram-lowreg-v1.json`](../../program/spectrogram-lowreg-v1.json)
(`version` `lowreg-spectrogram-v1`, self-hash `spec_sha256`
`880451c07c20f743323bf4303e95784a9dc0c84be5888daae215abdf4e0d260a`). Reference
implementation: [`scripts/lowreg_spectrogram.py`](../../scripts/lowreg_spectrogram.py).
Golden: [`tests/fixtures/lowreg-golden-v1.json`](../../tests/fixtures/lowreg-golden-v1.json).

Status: frozen reference for an **experimental** feature branch. Adoption:
**none** — no default, detector, profile or master changes. This is a feature
transform only: it restores no audio, separates no stem and identifies no note.
`pitch_resolution_claim: "none"`.

## Why a separate low-register branch

The project's nine-string instrument has a C1 low string near 32.703 Hz
(`program/instrument.json`; equal-temperament theory, not a measurement). The
xoxd default frontend (16 kHz, 400-sample window, 512 FFT, 31.25 Hz bins, first
HTK band near 64 Hz) cannot represent that string, and the xoxd 2021
reconstruction starts at 400 Hz ([XOD research](../research/XOD_SPECTROGRAM.md)).
This branch keeps 20–2000 Hz with no 80 Hz or 400 Hz floor, no high-pass and
no mains notch, at the cost of coarse time resolution.

## Definition

All arithmetic is IEEE-754 float64. Values in this table are normative; the
machine spec must carry the same values and the reference refuses a mismatch.

| Item | Value |
|---|---|
| Analysis rate | **8000 Hz**, mono. Multi-channel input: arithmetic mean of channels in float64 (each channel decoded first) |
| Input decode | PCM16 WAV, `int16 / 32768.0`. No DC removal, pre-emphasis, high-pass, notch or dither |
| Other rates | Refused by the v1 reference (exit 2). An external resample is an explicit caller pre-stage; its command, tool version and output sha256 are recorded (`--resampler-record`); its group delay is `null` (unmeasured) |
| Window | Periodic Hann, length 4096: `w[n] = 0.5 - 0.5*cos(2*pi*n/4096)` |
| n_fft | **4096** (512 ms support); one-sided bins j = 0..2048 at **1.953125 Hz** spacing |
| Hop | **160 samples = 20 ms** |
| Framing | No centre padding. Frame t uses samples [160t, 160t+4096); `n_frames = 1 + floor((N-4096)/160)`; N < 4096 refused |
| Time axis | Frame centre `(160t + 2048)/8000` s from the first analysed sample (first centre 0.256 s). Head [0, 0.256) s and the tail after the last centre are reported as partial-support `coverage`, plus unanalysed tail samples |
| Spectrum policy | **Power**: `P[t,j] = (Re X^2 + Im X^2) / 2048.0^2` (2048 = analytic periodic-Hann sum). No one-sided ×2 factor. Window-normalized power samples, not calibrated dBFS or SPL |
| Magnitude policy | **Not part of v1.** The filterbank is applied to power. `sqrt` of band power is not a magnitude filterbank and must not be labelled one. A magnitude variant needs a new spec version |
| Log bins | **24 per octave**, `f_k = 20 * 2^(k/24)` Hz, k = 0..159 (K = floor(24 log2(2000/20)) + 1 = 160). **fmin 20 Hz**, **fmax 2000 Hz**; last centre 1974.03 Hz |
| Filter shape | Triangle in Hz at each FFT bin frequency `f_j = 1.953125 j`: left half-width `L_k = max(f_k - f_k 2^(-1/24), 1.953125)`, right `R_k = max(f_k 2^(1/24) - f_k, 1.953125)`; weight `max(0, 1 - |f_j - f_k| / (L_k if f_j <= f_k else R_k))`; normalized to unit sum per filter |
| Band energy | `E[t,k] = sum_j W[k,j] P[t,j]` (ascending j) |
| Log output | `D[t,k] = 10 log10(max(E[t,k], 1e-10))` — absolute floor, not max-relative |
| PCEN input | `Z = E * 2^31` (xoxd power-scale convention; stated explicitly, not inherited) |
| PCEN params | **gain 0.98, bias 2, power 0.5, time constant 0.4 s, eps 1e-6** |
| PCEN smoother | `T = 0.4*8000/160 = 20` frames; `b = (sqrt(1 + 4T^2) - 1)/(2T^2)` ≈ 0.0487656; `M[0] = Z[0]`; `M[t] = (1-b) M[t-1] + b Z[t]` |
| PCEN output | `PCEN[t,k] = (Z[t,k] / (eps + M[t,k])^gain + bias)^power - bias^power` |
| PCEN state | **Causal; the smoother row M is carried across frames and across streamed blocks.** Block processing equals batch exactly; no reset on block boundaries |
| Output layout | Row-major frames × bands, float64 little-endian (`log_power_db.f64le`, `pcen.f64le`), each sha256-bound in `render.json` |

## Required caveats (stated in every output)

1. **Interpolated low bands.** Below about 68.61 Hz (left side) / 66.65 Hz
   (right side) the 24-per-octave spacing is narrower than the 1.953 Hz FFT
   spacing; each half-width is clamped to one FFT bin and the filter becomes
   linear interpolation between adjacent FFT bins (at most two taps). Adjacent
   low bands are **not independent measurements**.
2. **No pitch resolution claim.** The Hann main lobe spans ±3.9 Hz (two FFT
   bins) while a semitone at C1 is about 1.94 Hz. `pitch_resolution_claim` is
   `"none"`. Energy near 32.7 Hz is not C1 identification; a dominant spectral
   peak is not a played note, and note correctness cannot follow from it.
3. **Temporal blur; attack branch stays separate.** A 512 ms support holds
   ~16.7 C1 cycles but blurs a 178 BPM sixteenth (~84.27 ms) across ~6
   subdivisions. The 20 ms hop samples a 512 ms-smoothed trajectory; it is
   not 20 ms time resolution. The **short-window attack branch stays
   separate** (the existing log-mel rhythm frontend) and remains the only
   source of onset/timing evidence here; `onset_timing` is `null`.
4. **Baseline vs experimental.** Log-power `D` is this branch's baseline, and
   **log-mel remains video-utils' baseline frontend**. **PCEN is
   experimental**: prior fixed-knob work found default PCEN weaker than log-mel
   on several onset-invariance cases and better on others
   ([PCEN ablation](../agent-notes/2026-10-05-pcen-frontend-ablation.md)). v1
   fixes the knobs for reproducibility, not because they are recommended.
5. **Uncalibrated.** Values are on an uncalibrated digital scale; microphone
   response is unknown; denoise/profile history is `unknown` unless a caller
   binds the input to a run manifest.

## Output fields and explicit unknowns

`render.json` and the golden carry these fields; each `null` has a reason in
`null_reasons`.

| Field | Value |
|---|---|
| `spec_version` / `spec_sha256` | `lowreg-spectrogram-v1` / machine-spec self-hash |
| `input.sha256`, `sample_rate`, `channels`, `downmix`, `signal_version` | measured from the consumed file; `sha256_after_render` proves the input was not mutated |
| `pitch_resolution_claim` | `"none"` |
| `note_identity`, `intended_note_reference`, `tonic`, `mode` | `null` (no approved reference; spectral peaks are not notes) |
| `onset_timing` | `null` (use the separate short-window attack branch) |
| `temporal_support_seconds` / `hop_seconds` | 0.512 / 0.02, with `temporal_caveat` |
| `interpolated_below_hz` | `{left: 68.61…, right: 66.65…}` |
| `coverage` | head/tail partial-support seconds, unanalysed tail samples |
| `resampler`, `resampler_group_delay_samples` | `null` for native 8000 Hz input; otherwise the caller record and `null` delay (unmeasured) |
| `calibration` | `uncalibrated_digital_scale`; microphone response `unknown` |
| `denoise_or_profile_applied` | `unknown` |
| `pcen_status` | `experimental_fixed_knobs_not_tuned`; `baseline: log-power (log-mel remains project baseline)` |
| `listening_acceptance` | `not_assessed` |
| `adoption` | `none` |

## Conformance: golden fixture

A conforming implementation regenerates the deterministic fixture and matches
the golden with `math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)`.

- Fixture: 8000 Hz mono, 19,200 samples (2.4 s). Steady broadband
  `0.02 (2u - 1)` from SplitMix64 (seed 20261006, `u = (z >> 11) 2^-53`) plus a
  32.70319566257483 Hz harmonic tone (amplitudes 0.30, 0.15, 0.10, 0.06, 0.04,
  0.03; zero phase) gated silent until 0.6 s with a 10 ms linear attack;
  PCM16 with half-even rounding; 44-byte-header WAV. 0 clipped samples.
- `wav_sha256` `c812073a79715ec62e430f9d3268ac2bd1d9fb03e90f3c3f44633ca0d5631c61`;
  `pcm_sha256` `d1937ead464902c9763698f79486596f74a69e245de299c4ca0e3497d57d36d0`.
  Identity is checked by hash, so a libm last-ulp `sin` difference is absorbed
  by quantization or caught exactly.
- Geometry: 95 frames × 160 bands per matrix.
- Stored: full D and PCEN rows for frames {0, 17, 94}; full trajectories for
  bands {0 (20.00 Hz), 17 (32.68 Hz), 28 (44.90 Hz), 41 (65.36 Hz), 150
  (1522.19 Hz)}; full-matrix `math.fsum`/min/max per matrix. 1,910 values plus
  6 aggregates, no reduction; 42,035 bytes (≤ 50,000).
- The golden is written only by `golden --write` to a new path for a new spec
  version; tests never write it.

Commands (from the repository root):

```
python3 scripts/lowreg_spectrogram.py spec --sha
python3 scripts/lowreg_spectrogram.py fixture --out artifacts/s2/lowreg_spec_v4/fixture.wav
python3 scripts/lowreg_spectrogram.py render --wav PATH.wav --out-dir DIR [--backend numpy] [--resampler-record R.json]
python3 scripts/lowreg_spectrogram.py golden --check tests/fixtures/lowreg-golden-v1.json [--backend numpy]
```

`render` refuses (exit 2): non-8000 Hz, non-PCM16, fewer than 4096 samples,
existing output files, a symlinked input or output directory, and a machine
spec whose self-hash, version, parameters or fixture differ from the
reference. The API refuses non-finite samples.

## Versioning

Any change to a normative value, the spectrum/magnitude policy, the fixture,
stored indices or tolerance requires a new spec version, a new machine spec
and a new golden path. A magnitude-filterbank or tuned-PCEN variant is a new
version, never an edit of v1.
