# xoxd-spectrogram and PCEN for technical-guitar analysis

Reviewed October 5, 2026. The operator's “xod-spectrogram” resolves to the private
[`xoxd-ai/xoxd-spectrogram`](https://github.com/xoxd-ai/xoxd-spectrogram) repository,
main revision `8264a38651c785aa0dd9c02e3569b2d979747d80`. Its npm identity is
`@xoxd/spectrogram`, version 0.1.0; its Bazel module is `xoxd_spectrogram`.
The authenticated repository/API identity and isolated checkout agreed. Public
search did not locate it because it is private.

The core is useful as a reference and experimental frontend. Do not change the
current rhythm pipeline or audible master from this proof: naive default PCEN
produced weaker clean/mixture onset-envelope agreement in the selected synthetic
cases. Retain log-mel as the baseline, tune PCEN in a bounded ablation, and keep
phrase-window hypotheses as a separate factor.

## What can be reused

The [Svelte-free core](https://github.com/xoxd-ai/xoxd-spectrogram/tree/8264a38651c785aa0dd9c02e3569b2d979747d80/src/core)
has explicit FFT/window/mel conventions, causal PCEN state, deterministic mixup,
and committed Ruby-generated golden fixtures. `PcenState` retains its smoother
across frames; batch processing uses that same state implementation. The worker
advances PCEN even while the display is hidden, avoiding a reset when toggling
views. Those are good patterns for typed agent hooks and reproducible knob
comparisons. `PcenStep`, `MelFilterbank`, `FrameScrubber` and `RecordToTensor`
could later explain processing to the musician, once the report has a frontend
dependency budget and licensed integration route.

| Convention | xoxd default | Current video-utils rhythm backend |
|---|---|---|
| Analysis rate | 16 kHz | 16 kHz |
| Window / FFT | 400-sample periodic Hann / 512 | 1024-sample Hann / 1024 |
| Hop | 160 samples, 10 ms | 80 samples, 5 ms |
| Framing | No center padding; timestamps at window center | librosa centered frames |
| Mel bank | 40 HTK triangles, discrete unit-sum, 20–7600 Hz | 128 librosa Slaney bands, 27.5–8000 Hz |
| Spectrum | Power divided by squared window sum | librosa power mel, no equivalent window-sum normalization |
| Compression | Absolute 10 log10 floor or PCEN | Power dB relative to maximum |

These settings are not interchangeable. Record axes, scale, normalization,
centering, frame support and source offset in every feature artifact. The xoxd
2021 reconstruction starts at **400 Hz** and is unsuitable for our low strings.

## Algorithm and guitar-specific limits

PCEN divides each nonnegative spectral channel by a slowly varying energy
estimate, then compresses its range. The original paper evaluates keyword
spotting, not distorted guitar or audible restoration. Treat its robustness
results as a motivation for an experiment. [Wang et al., 2017](https://getreuer.info/papers/wang2017trainable/index.html)

The follow-up work studies parameter time scales and acoustic-event features in
noisy environments. A smoothing time suitable for stationary fan contrast may
also adapt to a sustained guitar tone; foreground salience is not note identity.
[Lostanlen et al., 2019](https://www.lostanlen.com/pubs/lostanlen2019spl/)

The pinned librosa 0.11 documentation warns that scaling matters and demonstrates
magnitude mel scaled by `2**31` for its default parameters. The xoxd reference
instead explicitly scales its normalized **power** by that factor. Preserve
that distinction and compare magnitude and power policies independently.
[librosa PCEN 0.11](https://librosa.org/doc/0.11.0/generated/librosa.pcen.html)

The xoxd default's 25 ms window contains only approximately 0.82 cycles of C1
at 32.703 Hz. Its first HTK band is centered around 64.24 Hz, and a 512 FFT at
16 kHz has 31.25 Hz bin spacing. Merely having `fmin=20` does not establish C1
pitch resolution. The existing 64 ms/1024 frontend has 15.625 Hz spacing and
also cannot qualify semitone identification near C1. Keep the short attack
branch and add a separate longer low-frequency branch, with explicit temporal
blur. At 178 BPM a quarter-beat subdivision is approximately 84.27 ms; a 256 ms
window cannot alone grade those attacks. Retain raw amplitude/low-band measures
and independent pitch evidence alongside contrast-normalized features.

PCEN is a feature transform. It does not supply an inverse that restores this
recording, a guitar stem, or an audible box-fan reduction. Do not attach its
feature attenuation to the master's measured noise-reduction claims.

## Dependency and license boundary

The package is private, with no explicit root LICENSE or SPDX license field.
Its [NOTICE](https://github.com/xoxd-ai/xoxd-spectrogram/blob/8264a38651c785aa0dd9c02e3569b2d979747d80/NOTICE)
says its license follows `xoxd_theme` and publication awaits operator
ratification. That statement does not identify a redistribution license.
Research execution on the operator's accessible repository is recorded here;
no package admission or source vendoring occurred. Establish the relevant
license authority before distributing that implementation.

The core FFT imports `fft.js` 4.0.4; NOTICE identifies it as MIT. The full package
also peers on Svelte, Skeleton, Tinyland color utilities and composables. Its
build uses Bazel/rules_js, Node 22.22.0, pnpm 10.13.1, TypeScript 6.0.3 and a
committed pnpm lock. Pulling that whole graph into the current Rust/Python
analysis runner would add unnecessary integration work. The bounded proof used
existing Bun 1.4.2 to execute the exact TypeScript PCEN file and existing locked
Python/librosa for the feature comparison; it installed nothing.

## Bounded local proof

The exact imported TypeScript PCEN core ran on three technical-v2 generated
cases, each with clean and mixed inputs, and the actual source's first 12 seconds.
NumPy reconstructed the xoxd window/FFT/mel rules and was checked against its
committed Ruby golden before use. This is not a run of its complete package test
suite or browser components.

- Maximum Ruby log-mel difference: `4.931166586175095e-12` dB.
- Maximum Ruby default PCEN absolute difference: `8.36664071357518e-12`.
- Exact TypeScript batch versus streamed PCEN difference: zero.
- Six generated WAVs and one full decoded-source WAV had unchanged hashes.
- Two numeric threads; final proof completed in 6.02 seconds.

The following cosine similarities compare the clean and mixed spectral-flux
envelopes, computed without using generator labels to select onsets. They are
an exploratory invariance diagnostic, **not precision, recall or phrase accuracy**.

| Generated case | Power log-mel baseline | Same power + default PCEN | Magnitude log-mel | Magnitude + default PCEN |
|---|---:|---:|---:|---:|
| Low C1 sustain | 0.37250 | 0.09744 | 0.37905 | 0.07779 |
| Palm-muted recurrence | 0.57488 | 0.37677 | 0.55728 | 0.28475 |
| Legato recurrence | 0.36102 | 0.21705 | 0.37563 | 0.13415 |

These default policies reduced this metric on every selected case. Clicks,
fan-like generated noise, scaling, smoothing and the metric itself may explain
the change. This small experiment does not reject tuned PCEN generally.
Actual-opening onset candidate counts were 36 for baseline power log-mel,
29 for paired power PCEN, and 31 for documented magnitude PCEN. There are no
reviewed onset labels for that excerpt; fewer candidates is not better accuracy.

The proof used decoded source WAV SHA
`d68e49688293b1fb8c7c2566e2ecd6e31df9972af013dd23454e15864654bd2a`
from the original movie SHA
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.
It did not reprocess the cleaned video, change markers, update latest pointers,
modify the analysis environment, or edit sibling repositories.
The exact evidence and worker hashes are in
[`2026-10-05-xod-spectrogram.md`](../agent-notes/2026-10-05-xod-spectrogram.md).

The existing pilot's 1.3483-second motifs can be mismatched by a shortest
four-pulse recurrence window at the detector's half-time pulse, approximately
2.6968 seconds. Fix or ablate that window hypothesis independently; no PCEN
frontend improvement can be inferred from that discovery failure.
