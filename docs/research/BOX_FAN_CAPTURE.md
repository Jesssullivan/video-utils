# Box-fan capture: actual short-interval characterization

Checked October 5, 2026. A large box fan is operator-stated context; its model,
speed, blades, motor, microphone position and recorded gain processing remain
unknown. The source's three short quiet candidates are **not verified fan-only
audio**. Their spectral peaks cannot identify played notes or fan RPM.

## Bound source and method

Read only the original decoded mono float32 WAV from the frozen conservative3
run, using native 44,100 Hz samples at 4.10–4.95 s, 149–150 s and 0–1 s. The
selected samples total 2.85 seconds. The original recording and decoded WAV
hashes matched before/after; no audio derivative/filter was generated. Two
numeric threads; the first worker completed in 1.52 seconds. Exact source
identity, measurements and reproduction are in the
[dated receipt](../agent-notes/2026-10-05-box-fan-capture.md).

PSD uses Hann Welch windows of 16,384 native samples, 8,192 overlap, no
detrending, density scaling and no zero padding. Bin spacing is **2.692 Hz**;
each window spans about 0.372 s. Capture has only three overlapped periodograms,
the other intervals four; these are not independent averages. Integrated band
power is the sum of PSD bins × bin spacing, lower-inclusive/upper-exclusive.
PSD is dBFS/Hz, integrated power is dBFS, and whole-interval RMS is dBFS.
[SciPy Welch documentation, accessed 2026-10-05](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html).

The selected 0.85-second support has a full-interval Fourier spacing limit of
about 1.18 Hz even before window broadening; this Welch choice is coarser.
Sub-Hz estimates, narrow physical linewidths, exact tuning or precise RPM are
unsupported. Report rounded bins/ranges rather than treating computed FFT
coordinates as frequency accuracy.

## Measured interval differences

| Source measurement, dBFS | Capture 4.10–4.95 s | Tail 149–150 s | Opening 0–1 s |
| --- | ---: | ---: | ---: |
| Whole-interval RMS | −35.35 | −34.30 | −25.10 |
| 20–45 Hz power | −65.34 | −62.63 | −59.32 |
| 45–120 Hz power | −48.95 | −45.86 | −38.35 |
| 120–250 Hz power | −38.72 | −41.77 | −27.38 |
| 250–1000 Hz power | −39.00 | −38.91 | −28.84 |
| 1–2 kHz power | −47.32 | −40.86 | −45.60 |
| 2–8 kHz power | −49.87 | −41.53 | −47.06 |
| 8–16 kHz power | −61.43 | −56.56 | −62.90 |

Opening total RMS is 10.24 dB above capture, but spectral changes are uneven:
120–250 Hz is 11.34 dB higher, 250–1000 Hz 10.16 dB higher, and 2–8 kHz only
2.81 dB higher. Tail total RMS is only 1.05 dB above capture while 2–8 kHz is
8.34 dB higher. This is not one identical recorded spectrum multiplied by a
single gain. It does not establish whether changes arise from music, clicks,
handling, fan sound, microphone/room changes or capture processing.

Split each interval into five equal nonoverlapping blocks: 0.17-second capture
blocks and 0.20-second tail/opening blocks. Whole-block RMS ranges are 2.37,
2.72 and 2.69 dB respectively. Short-block 20–45 Hz periodogram ranges are
11.86, 5.62 and 7.30 dB; 2–8 kHz ranges are 3.99, 10.05 and 5.34 dB. Those
short spectra are noisy estimates (about 5.88/5 Hz bins and no averaging), so
these ranges are descriptive variability, **not a statistical stationarity
test or proof that fan output itself changed**.

## Peaks and musical overlap

| Interval | Largest 20–45 Hz bin | Status | Stronger local peaks below 1 kHz, rounded Hz |
| --- | --- | --- | --- |
| Capture | 43 Hz | Rising band edge; not a local PSD maximum | 175, 269, 199, 156, 312, 390, 339, 299 |
| Tail | 43 Hz | Rising band edge; not a local PSD maximum | 156, 118, 312, 129, 272, 390, 234, 240 |
| Opening | 43 Hz | Local maximum; apparent half-power crossing bracket about 40–49 Hz | 167, 175, 307, 336, 129, 234, 266, 199 |

Local peaks are ranked by PSD among maxima with at least 3 dB prominence in
10–1000 Hz. Capture's four strongest apparent half-power crossing brackets
are approximately 170–178, 266–275, 196–202 and 151–159 Hz. Tail's are
153–159, 116–124, 307–315 and 127–132 Hz; opening's 162–170, 170–178,
304–312 and 331–339 Hz. Their 5.4–8.1 Hz apparent widths are coarse,
window-limited crossing brackets, not measured physical fan linewidths.
Do not assign a linewidth to the capture/tail band-edge maximum.

The nearest theoretical C1 bin is 32.30 Hz. It is not a local PSD maximum in
any of these three estimates; its density is −81.28, −83.17 and −80.79
dBFS/Hz respectively. This does **not** prove C1 is absent or safely removable:
weak/masked musical energy can lack a visible peak, and these gaps do not
represent every active passage.

The exact operator tuning remains in
[`program/instrument.json`](../../program/instrument.json). Inferred octaves
and theoretical A4=440 frequencies give C1 32.703 Hz, F1 43.654 Hz, Eb2
77.782 Hz, Eb3 155.563 Hz and Ab3 207.652 Hz. A recorded 43 Hz feature is near
F1; tail local bins near 78/156/234/312/390 Hz are close to the harmonic series
of theoretical Eb2. Capture also has 156/312/390 Hz peaks. This is an
**overlap/contamination ambiguity**, not identification of an Eb note or a fan
harmonic family. No isolated 207.652 Hz Ab3 component follows from a nearby
199 Hz peak. [UNSW frequency equations](https://phys.unsw.edu.au/jw/notes.html).

## Fan mechanism and restoration implications

Rotating machinery can produce rotation/blade-pass components and harmonics,
while turbulence contributes broadband sound. Blade-pass frequency depends
on actual blade count × RPM/60; neither input is known here. Manufacturer
examples of motor hum do not establish mains lines in this recording.
[LONGWELL mechanism reference, updated 2026-08-23](https://www.longwellfans.com/resources/blade-pass-frequency-calculator/).
NASA's fan-noise work models broadband sources from turbulent flow and blade/
vane interactions; its turbofan scope supports a general mechanism, not a
household fan's frequency or level.
[NASA broadband fan-noise report](https://ntrs.nasa.gov/citations/20110003467).

The time-varying recorded mixture and spectral mismatch help explain why the
captured profile could reduce selected/tail windows more than the opening.
Earlier independent measurements found captured8/12 opening RMS reductions
only 0.556/0.573 dB despite 4–5 s reductions 4.445/5.433 dB. This is a
plausible filter/input explanation, not a measured causal model. Phone/camera
AGC is a possible confounder; its activation, gain history and contribution
have not been verified. Do not relabel opening's extra mid/low energy as fan
noise merely to justify stronger subtraction.

Keep captured8-clarity/main and captured12/alternate as root's auditions, not
accepted masters. Review low palm mutes, sustain and removed residue: prior
active 20–45 Hz mixture losses of about 2–3 dB remain unresolved. These short
PSD observations authorize no 32 Hz subtraction, automatic noise-only label,
notch or speech-model default. A longer operator-reviewed fan-only sample and
separate guitar/noise calibration would reduce ambiguity in a future take;
the current mono mixture cannot certify that separation.
