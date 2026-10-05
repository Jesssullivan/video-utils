# Primary research: metronome candidate isolation

Checked 2026-10-05. This is an engineering experiment for distorted nine-string
guitar with intentional approximately 32 Hz fundamentals; no source establishes
that the user recording can be separated transparently.

## Methods supported by upstream documentation

[SciPy cross-correlation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.correlate.html)
provides direct/FFT correlation and a matched-filter example. Matching a supplied
click waveform is therefore a reproducible baseline. Normalization and local
native-rate refinement are this repository's engineering additions; a strong
match indicates resemblance, not verified metronome identity.

[SciPy bounded least squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)
supports constrained optimization and robust losses. A single scalar waveform
gain has a closed-form least-squares solution; the prototype can bound that gain
and inspect the remaining residual without a heavyweight optimizer. Residual
energy is an overlap warning, not an instrument classifier.

[Audacity Click Removal](https://manual.audacityteam.org/man/click_removal.html)
targets clicks such as those on vinyl recordings and warns that aggressive
threshold or spike-width settings can falsely detect clicks and damage audio.
That is a concrete reason to avoid blanket declicking on pick attacks and
percussive palm mutes. A regularly recorded metronome is a different target from
an isolated recording defect.

[FFmpeg adeclick](https://ffmpeg.org/ffmpeg-filters.html#adeclick)
is available as an alternative impulse-noise repair experiment. It is not the
default here: generic impulsive-event repair does not provide a guitar-versus-
metronome decision or the user-specific overlap evidence this lane needs.

[librosa HPSS](https://librosa.org/doc/main/api/generated/librosa.decompose.hpss.html)
separates harmonic and percussive spectrogram content. Both metronome clicks and
guitar attacks can be percussive; deleting that component is not click isolation.

## Chosen prototype and claim boundaries

Use a click-only interval supplied by the operator, candidate correlation,
bounded native waveform fitting and conservative overlap abstention. Default
to detection only. Subtraction is capped at 50 percent and independently protects
low-frequency subtraction-estimate bins; no high-pass is applied to the master.

The protected-band operation and acceptance thresholds are design choices to be
tested with known synthetic sources. Protection of DFT bins is a measurable
frequency-domain property, not evidence that all attack articulation or room
decay survives. Filtering the sparse estimate can produce ringing. Save the
estimate/residue and a processed variant for matched-level listening.

Mono mixtures are underdetermined. Clicks that overlap a pick attack, share a
similar spectrum, change timbre through accents or pass through recorder AGC
may be inseparable by this method. Abstention is useful evidence. Never name an
estimated component a recovered original metronome or clean guitar track.
