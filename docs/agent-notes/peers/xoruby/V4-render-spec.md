# V4 low-register render spec — peer summary for xoruby

Sprint `20261006-s2`, lane `lowreg_spec_v4`, Linear TIN-5608 (peer request V4
under TIN-5186). Prepared on branch `sprint/20261006-s2/lowreg_spec_v4`; root
audits, signs the merge and makes the TIN-5186 post. The hashes below are
valid for the merged files; re-check them after merge. Authority:
R-HOOK-CONVERGENCE-20261004 (R-N13 receipts).

Nothing in this note or in the referenced files is derived from the real take.
All values come from a deterministic generated fixture.

## What V4 is

A separate, low-register-only spectrogram feature branch: 8000 Hz mono,
periodic Hann n_fft 4096 (512 ms, 1.953125 Hz bins), hop 160 (20 ms), no
centre padding, 160 log-spaced bands at 24 per octave from 20 Hz to
1974.03 Hz (fmax 2000 Hz), power spectrum normalized by the window sum squared
(2048^2), unit-sum triangular filters, `D = 10 log10(max(E, 1e-10))`, and PCEN
on `Z = E * 2^31` with gain 0.98, bias 2, power 0.5, time constant 0.4 s,
eps 1e-6, `M[0] = Z[0]`, causal state carried across frames and blocks (block
equals batch exactly). No 400 Hz or 80 Hz floor, no high-pass, no mains notch.
Magnitude filterbanks are not part of v1.

## Required statements

1. **Spec**: [`docs/spec/LOW_REGISTER_SPECTROGRAM_SPEC.md`](../../../spec/LOW_REGISTER_SPECTROGRAM_SPEC.md)
   (prose) and machine spec [`program/spectrogram-lowreg-v1.json`](../../../../program/spectrogram-lowreg-v1.json):
   self-hash `spec_sha256` `880451c07c20f743323bf4303e95784a9dc0c84be5888daae215abdf4e0d260a`
   (canonical JSON without the `spec_sha256` key; `python3 scripts/lowreg_spectrogram.py spec --sha`);
   file sha256 `ed6ce97a37c749490002c0ce7cdc3a3e562386d0cb3100d6899464b66a15d2e5`.
2. **Golden**: [`tests/fixtures/lowreg-golden-v1.json`](../../../../tests/fixtures/lowreg-golden-v1.json),
   file sha256 `e090de4dacfec805945f0b737ce29f3ece0c73318393d5a5b47213211bef57e4`,
   42,035 bytes, 1,910 stored values + 6 aggregates, tolerance
   `math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)`. Fixture `wav_sha256`
   `c812073a79715ec62e430f9d3268ac2bd1d9fb03e90f3c3f44633ca0d5631c61`,
   `pcm_sha256` `d1937ead464902c9763698f79486596f74a69e245de299c4ca0e3497d57d36d0`
   (32.703 Hz fundamental + 5 harmonics + steady SplitMix64 broadband, seed 20261006).
3. **Log-mel remains video-utils' baseline frontend**; log-power `D` is this
   branch's own baseline.
4. **PCEN is experimental** (`experimental_fixed_knobs_not_tuned`): knobs are
   fixed for reproducibility, not recommended; prior fixed-knob work found
   default PCEN weaker than log-mel on several onset cases.
5. **The short-window attack branch stays separate.** The 512 ms support blurs
   a 178 BPM sixteenth (~84.27 ms) across ~6 subdivisions; the 20 ms hop is not
   20 ms time resolution. `onset_timing` is `null` in every V4 output.
6. **`pitch_resolution_claim: none`.** The Hann main lobe is ±3.9 Hz while a
   C1 semitone is ~1.94 Hz, and bands below ~66.65/68.61 Hz are interpolations
   of adjacent FFT bins. Energy near 32.7 Hz is not C1 identification; a
   dominant peak is not a played note. `note_identity`, `tonic`, `mode` and
   `intended_note_reference` are `null`.

## How to conform

Regenerate the fixture from the formulas in the spec (stdlib integers and
`sin`), confirm both fixture hashes, render 95 × 160 matrices for D and PCEN,
and compare the stored rows (frames 0, 17, 94), trajectories (bands 0, 17, 28,
41, 150) and full-matrix fsum/min/max at the stated tolerance. The reference
stdlib and numpy backends agree on all 30,400 cells (largest absolute
difference about 4.7e-12 on this fixture).

## Not claimed

Adoption: none. No listening assessment, no real-take render, no detector,
profile or master change, no calibration (uncalibrated digital scale,
microphone response unknown). Construction checks on the fixture (C1-region
band rises 58.50 dB from pre-onset to sustained; 55.09 dB above the 44.90 Hz
band) are sanity checks on generated data, not guitar evidence.
