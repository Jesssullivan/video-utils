# Tonal-context research, October 5, 2026

The implementation compares hypotheses; it does not classify a deathcore take
as a definite Western major/minor key. Research was read online before worker
implementation. No Essentia package, weights or notebook material is installed
or copied.

**Profile correlation.** Krumhansl–Schmuckler compares a pitch-class histogram
with shifted major/minor profiles. The maintainer's [Humdrum keycor
documentation](https://extras.humdrum.org/man/keycor/) publishes the
Krumhansl–Kessler numerical profiles, correlation definition and alternate
profile families. We use those measured profile numbers as a transparent
comparison baseline, not a likelihood or genre-trained estimator.

**Repeated-note bias and ambiguity.** [Temperley's original 2002
paper](https://davidtemperley.com/wp-content/uploads/2015/11/temperley-maai.pdf)
describes duration-vector matching, altered profile values, short-segment pitch
presence and contextual key-change penalties. We independently implement its
published profile values for a second comparison. We expose mean normalized
chroma and a separate pitch-presence aggregate instead of counting duplicated
harmonics or rapidly repeated attacks as independent tonal votes. No Bayesian
posterior or dynamic key-state model is implemented. Local ranking stability is
a diagnostic, not validation of a modulation or tonic.

**Actual feature meaning.** [librosa 0.11.0 chroma_stft
documentation](https://librosa.org/doc/0.11.0/generated/librosa.feature.chroma_stft.html)
defines octave-folded, normalized chroma, centered frame timing, optional tuning
estimation, and octave weighting. The existing analysis matrix uses its default
octave weighting. Consequently the tuning registry and a visible C1 harmonic
cannot establish a played C1 fundamental. With 4096 FFT samples at the current
16 kHz rate, bins span 3.90625 Hz, wider than the approximately 1.945 Hz
C1-to-Db1 spacing. This numerical limitation is computed from the configured
rate and equal temperament, not a claim made by librosa. Dense distortion,
clicks and noise can dominate pitch-class salience.

**Alternative comparator.** [Essentia Key
documentation](https://essentia.upf.edu/reference/std_Key.html) offers multiple
profile types, a best-versus-second score, harmonic contributions and an
ambiguous major/minor option. Its major/minor output is insufficient for a
modal/chromatic riff by itself. Essentia remains an optional research comparator;
the present worker has no Essentia runtime dependency.

**Project-specific decisions (inferences).** Seven diatonic masks give
scale-collection coverage, with all tied rotations retained. A complete C-major
collection equally fits D-Dorian, E-Phrygian and the other rotations: inventory
alone cannot select their tonic. Sparse one/two-class material, short context,
near-uniform chroma and silence abstain. Even a stable triad-shaped spectrum
can be harmonics 2, 3 and 5 of a missing C1 fundamental, rather than three
played notes. Tonic/mode remain null; ranked hypotheses and recurrence-window
distribution similarities guide listening. This lane applies no score-based
note-error grading and never infers intended pitch from the custom open tuning.

Thresholds are explicitly heuristic and uncalibrated for distorted nine-string
guitar. Synthetic transposition and abstention fixtures validate bookkeeping;
they do not establish real-take tonic, notes, meter or musical correctness.
