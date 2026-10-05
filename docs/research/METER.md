# Meter, accent cycles and pulse ambiguity

Research checked October 5, 2026.

The official [librosa 0.11 beat tracker](https://librosa.org/doc/0.11.0/generated/librosa.beat.beat_track.html)
returns tempo and beat positions using onset strength and dynamic programming;
those outputs do not establish a time signature. We reuse existing feature
evidence rather than invoke a second unrestricted audio/model pipeline.

The [FMP beat tracking notebook](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C6/C6S3_BeatTracking.html)
explains a roughly constant-tempo/onset model and illustrates failures when
strong onsets disagree with the intended beats. The [FMP local pulse notebook](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C6/C6S3_PredominantLocalPulse.html)
explicitly distinguishes multiple perceptual pulse levels. Our inference is to
retain fitted half/double aliases and expose accent cycles separately from
notated quarter/eighth-note hypotheses.

[Krebs, Böck and Widmer, ISMIR 2013](https://www.cp.jku.at/research/papers/Krebs_etal_ISMIR_2013.pdf)
jointly model beat, downbeat, tempo, meter and rhythmic patterns using a learned
HMM. Their annotated ballroom evaluation contains constant 3/4 and 4/4 meters;
it does not validate nine-string deathcore, odd additive meters, tapping or
sweeps. The paper motivates multiband accent evidence and highlights
syncopation/triplet ambiguity. No paper code or trained weights are copied.

The present worker fits cyclic means to MFCC0 energy proxies and checks their
repeatability across held-out cycles. Its thresholds are conservative engineering
heuristics, not probability calibration. Distortion, compression and metronome
bleed can alter accents. A repeated seven-unit cycle may be 7/8, a riff motif,
or cross-rhythm; counts alone do not prove a notated meter. Additive partitions
are withheld unless identifiable, and notation remains unknown. Changing local
rankings indicate nonstationary evidence rather than confirmed mixed meter.
