# Low-tuned nine-string guitar: measured features and claim boundaries

Research checked October 5, 2026. Operator context is deathcore/technical guitar,
nine strings, with the lowest fundamental approximately 32 Hz. Actual tuning,
intended notes, articulation and rhythm still require an approved reference.

## Why low tuning changes the defaults

A 32 Hz period is 31.25 ms: a 10–20 ms onset window does not contain even one
complete lowest-string period. This is arithmetic, not a claim that the phone
microphone captured that fundamental. Distortion produces harmonics; a prominent
64/96 Hz spectral component does not establish the played string or octave.
Do not apply a speech-style high-pass or infer nuisance hum from energy near a
musical fundamental. Evaluate low-band attenuation and listen to removed residue.

The baseline pitch comparison for the week is YIN/pYIN configured deliberately
below 32 Hz rather than copied from a speech or standard-guitar example. The
[librosa pYIN documentation](https://librosa.org/doc/0.11.0/generated/librosa.pyin.html)
requires explicit `fmin`/`fmax`, recommends approximately 65 Hz as a minimum in
its example, and notes lower values may be feasible. The
[pYIN paper](https://webspace.eecs.qmul.ac.uk/s.e.dixon/pub/2014/MauchDixon-PYIN-ICASSP2014.pdf)
models candidate frequencies and voicing; it is not evidence of accurate
polyphonic transcription of this guitar take. Validate distortion, weak/missing
fundamentals, harmonics, chords, palm mutes and transient clicks separately.

## Implemented stdlib pilot

`scripts/guitar_features.py TOOL INPUT --run-dir DIR` supports `noise`, `tone`,
`notes` and `phrases`. It preserves input media and writes one local JSON file
per tool atomically, with the same JSON on stdout. FFmpeg decoding is a separate
mono 16 kHz floating-point analysis copy; the working master keeps its rate and
channels. Inputs must have known duration at most 300 seconds. FFmpeg is bounded
to two threads and a 300-second timeout; FFprobe has a 30-second timeout.
All frame/sample settings and executable commands are recorded.

- **Noise:** 500 ms RMS windows, lowest 10% capped at 20 candidate intervals,
  plus measured spectra. Quiet is not synonymous with noise-only. The
  [Audacity noise reduction manual](https://manual.audacityteam.org/man/noise_reduction.html)
  requires a noise-only profile and recommends inspecting residue for removed
  wanted audio. An agent must ask for listening/reference evidence before
  promoting a candidate into a restoration profile.
- **Tone:** demeaned Hann-window FFT measurements for 28–80, 80–250,
  250–2000 and 2000–8000 Hz bands. Frames are 4096 samples (256 ms), sampled
  once per second. Energy uses squared FFT magnitude with window-energy
  normalization. Bins are 3.90625 Hz apart; the protected
  28–80 Hz guard band includes the main FFT lobe of the expected 32 Hz lowest
  fundamental instead of treating 32 Hz as a hard lower measurement boundary.
  Leakage and coarse band edges still limit interpretation. These are sampled
  mixture measurements, not quality judgments or source-specific measurements.
- **Notes:** zero-padded FFT normalized autocorrelation in at most 120 sparse
  256 ms frames, looking for strong repeats between 28 and 1000 Hz. The
  shortest repeat within 95% of the strongest qualifying local maximum is a
  candidate; the score is not a probability. This is **not YIN**. Harmonic and
  octave ambiguity remain. Notes, exact string tuning, intended notes, tonic,
  mode and polyphonic transcription remain unsupported/unknown. Sparse
  snapshots do not provide a continuous note track and can miss attacks.
- **Phrases:** low-energy gaps of at least one second and normalized similarity
  above 0.9 between nonoverlapping eight-second amplitude-envelope regions.
  Regions advance by four seconds; at most 20 strongest recurrence proposals
  are retained. Matching loudness shapes do not establish the same riff.
  Outputs include proposed review spans with uncertainty, never automatic
  mistakes. Same-source `analysis.json` and `notes.json` DAG context is used
  when available; source-hash mismatch or malformed context is rejected.

The operator clarified that “phase” meant musical **phrases**. This pilot does
not attempt electrical channel-phase diagnostics. The intended DAG is
restoration → click/tempo candidates → tonal/phrase hypotheses → confirmed
recurrence/reference comparison → bounded timeline review markers. Today tonic
and mode abstain, so they cannot silently become recurrence-selection truth.

## Validation and next benchmark

Synthetic fixtures verify that a 32 Hz tone stays measurable in the protected
low band, strongly distorted 32 Hz periodicity is recovered within 0.2 Hz,
a 220 Hz tone is not silently halved, silence abstains, quiet guitar is not
classified as noise, and gap/recurrence proposals remain ungraded. These are
source-level algorithm checks, not demonstrated pitch accuracy on the demo.

Next compare full-resolution YIN/pYIN and guitar-specific methods against
hand-annotated passages with exact tuning and intended rhythmic phrases.
Report onset uncertainty, octave errors, false repeated phrases, and abstention
rates separately. Onset/rhythm events need finer windows than low-note pitch;
use separate parallel analysis representations rather than forcing one window
to serve both. Graphical video overlays and future Final Cut/Resolve exports
consume timestamped review spans, preserving source offsets and uncertainty.

## Actual take pilot receipt

All four workers ran successfully against the first restoration run's
`denoised.wav` (SHA-256
`c9a75b6cc1e2da37f2ef79e8f70ddb452939e453eb940540b9f2b71a7d9a737c`).
Private results are in `artifacts/feature-pilot/`; this is an analysis receipt,
not listening acceptance. The input mixture measured −21.136 dBFS RMS.
Twenty low-RMS candidate windows were returned. The tone pilot measured 151
frames; approximately 1.05% of sampled AC energy fell in 32–80 Hz and 53.96%
in 80–250 Hz. This neither establishes nor rules out any intended low note.
Of 120 sparse periodicity frames, 14 passed the strong-repeat heuristic; they
remain source-ambiguous candidates. Phrase analysis proposed zero gaps and
zero repeated-envelope regions at the fixed thresholds, and abstained from
phrase judgment. The accompanying ten unit tests passed. No model was
installed, no media was changed, and no tuning/tonic/mode was inferred.


### Canonical derivative timeline inheritance

When the run directory contains a media `manifest.json`, the worker inherits
the original audio-stream offset only if the input SHA-256 matches a recorded
`source.wav`, `denoised.wav` or `cleaned.wav` hash. It requires explicit
`no_time_stretch`, matching sample rate/channels, and decoded duration matching
the canonical PCM sample count within two analysis samples. Otherwise it keeps
the independently probed input timeline and records a rejection reason. Lineage
records the input and original recording hashes, canonical PCM description and
manifest path. A filename alone never establishes timeline inheritance.
The actual-take measurement receipt above used the earlier 32–80 Hz band; new
runs explicitly label the protected 28–80 Hz guard band.

## Automatic phrase backend (optional locked librosa)

The operator requested automatic phrase/bar/breakdown discovery without
predeclared intent. `phrases --backend librosa --bpm 178` enables an independent
feature-segmentation pilot; the take's 178 BPM seed is operator supplied. With
no explicit seed, a same-source rhythm artifact may supply a periodicity
candidate. Tempo is a pulse grid, not an expected score or proof of time
signature. The stdlib backend remains an envelope baseline.

The backend extracts 11 MFCC coefficients excluding the energy coefficient,
12 chroma dimensions, spectral centroid, flatness and log RMS from 256 ms FFT
windows at a 16 ms hop. Mel analysis starts at 28 Hz. It aggregates median
features into pulse intervals, scales varying dimensions, and compares feature
changes across four-pulse windows plus a smaller two-pulse term. Local novelty
peaks above a robust threshold, separated by at least four pulses, propose
section boundaries. These can occur in a continuously played riff without any
pause. Descriptive region labels use feature similarity, relative spectral
brightness and candidate onset density, not declared intent.

Nonoverlapping 4/8/16-pulse feature sequences are compared by cosine similarity;
up to 60 deduplicated candidates above 0.8 are returned, with relative onset
candidates for recurrence self-consistency review. The 0.8 score is an
experimental operating threshold, not a confidence probability. Four-pulse
“bar proxies” are a separate unlabeled-meter grouping hypothesis. No automatic
technique diagnosis is claimed: a bright ending is not sufficient evidence of
sweeping, tapping or legato, and a low-register texture is only a possible
breakdown. Tonic/mode abstain because distorted mixture chroma is not yet
validated against annotated material.

The feature design is informed by official
[librosa MFCC documentation](https://librosa.org/doc/0.11.0/generated/librosa.feature.mfcc.html)
and its
[recurrence-matrix documentation](https://librosa.org/doc/0.11.0/generated/librosa.segment.recurrence_matrix.html).
This worker implements explicit cosine sequence comparisons rather than
claiming to call `recurrence_matrix`. Automatic structural hypotheses and
relative recurrence discrepancies require no intended score; definitive wrong
notes, skipped intended events and performance grades still require suitable
reference evidence. Tests include repeated note features and a different-note
riff with an unchanged amplitude envelope, plus silence/constant-feature
abstention. Optional tests run in the locked analysis environment.

First actual automatic pilot on the hash-verified denoised derivative returned
44 texture-region candidates, ten recurrence pairs, 112 four-pulse bar proxies,
and 552 onset candidates. This differs from the envelope baseline's zero
proposals because spectral/chroma structure can change without pauses. These
counts are a feasibility receipt, not segmentation accuracy. That first run
records the two-pulse novelty prototype; the current four-pulse plus 0.3-times
two-pulse variant fixes a synthetic continuous-riff boundary failure and
requires the final root pipeline run to refresh the artifact. All 15 feature
tests pass in the locked analysis environment, including the optional two
NumPy segmentation tests. No learned model or GPU is used.
