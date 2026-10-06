# Guitar restoration and performance analysis

Approved direction, October 5, 2026. Private repository:
`Jesssullivan/video-utils`. Work is tracked in a dedicated Tinyland Linear
project; published project and issue IDs belong in `program/linear.json`.

The user's instrument is always a downtuned nine-string guitar, with a lowest
fundamental around 32 Hz, used for deathcore and technical virtuoso playing.
Default restoration must retain that fundamental. Do not introduce an 80 Hz
high-pass or treat low-frequency hum-like content as noise without evidence.

The operator confirms the constant low-to-high pitch classes **C F Bb Eb Bb Eb
Ab C F**. Register them in `program/instrument.json`, numbered strings 9→1.
The octave interpretation is **C1 F1 Bb1 Eb2 Bb2 Eb3 Ab3 C4 F4**, with MIDI
**24, 29, 34, 39, 46, 51, 56, 60, 65**. These octaves are inferred from the
approximately 32 Hz lowest string, the highest F being a semitone above standard
high E4, and ascending order; they are not measured tuning or detected notes.
Preserve every supplied interval, particularly Eb2→Bb2, rather than normalizing
to a familiar all-fourths tuning.

Theoretical frequencies use A4=440 Hz and
`frequency_hz = 440 * 2 ** ((midi - 69) / 12)`, giving C1≈32.703 Hz and
F4≈349.228 Hz. [UNSW documents the note/MIDI/frequency relationship](https://phys.unsw.edu.au/jw/notes.html);
[Fender documents standard guitar tuning](https://www.fender.com/articles/setup/standard-tuning-how-eadgbe-came-to-be).
Registered instrument context supplies analysis priors; it does not establish
the notes played, tonic/mode, or note correctness in this recording.

The operator also makes the **large box fan background** and artist tone
references project constants: **Lorna Shore, The Haunted, Meshuggah, Kublai Khan
TX, Mgła and Children of Bodom**. Their machine-readable context is
`program/capture-context.json`, separate from the fixed tuning registry so existing
tuning-bound analysis remains intact. Use these references for articulation,
string separation, low-register weight, saturation and sustain. Measure each
take's fan spectrum and capture interval rather than copying a studio/full-band
EQ curve or assuming motor/mains frequencies.

Evening listening feedback identifies the initial conservative demo as too mild.
The next audio iteration needs reviewed opening noise capture applied to the
whole take, stronger denoising comparisons, controlled compression and bounded
frequency-response/clarity trials. Preserve old renders, pure denoise/residue
evidence, 32Hz content, pick attacks and tails. The marked video preview should
use the improved iteration after source, timeline and peak checks; callouts remain
musical review hypotheses. Existing calibration and AU lanes continue in parallel.

## Deliverables and architecture

By **6:00 p.m. America/New_York on October 5**, produce an auditionable iteration
of the provided trimmed take: a source comparison, conservative cleaned WAV,
video export with preserved picture/timeline, rhythm estimates, and an evidence
report. The audio target is −18 LUFS integrated and −1.5 dBTP. Retain the original
sample rate and channel count. Do not overwrite or commit original media.

Rust owns orchestration, typed run records, and reusable DSP. FFmpeg owns
decode/filter/encode and loudness measurement. Bounded Python provides offline
analysis, initially without mandatory model downloads. R/Quarto supplies
reproducible research reports with a plain HTML fallback. Nix and committed
dependency locks define the development environment. `just` is the operator
entrypoint. Zig is deferred until an interoperability or measured performance
need justifies a separate component.

The recipe contract is `doctor`, `demo INPUT`, `clean INPUT PROFILE`,
`analyze INPUT`, `report RUN_DIR`, `export RUN_DIR`, `test`, `check`, and
`model-prefetch MODEL`. The Rust CLI exposes `probe`, `clean`, `demo`, `export`,
`analyze`, and `report`. A demo proceeds through source inspection, clean/export,
rhythm analysis, and reporting. Local artifacts are isolated per run under
`artifacts/runs/`; provenance records source identity, commands, tool versions,
profile parameters, analysis resampling, and output measurements.

The current versioned tool/API contract, local MCP stdio adapter, and twenty-five
per-tool skills expose the same bounded operations. Agent guidance connects research evidence
to explicit, auditable parameter suggestions for noise, tone, and note analysis.
Suggestions require comparative evaluation; agents cannot silently change the
accepted profile or manufacture intended-note references.

## Evidence-guided priorities for the following week

The enhanced October 5 take now has stronger captured-noise comparisons, mild
EQ/compression, a synchronized marked preview and mobile playback evidence.
These are audition and review artifacts; they do not close musical-quality work.
Retain the 35-hour core and optional 35-hour extension below, with these concrete
risks directing the allocations:

- Prioritize phrase precision and boundary accuracy before adding more flags.
  The generated baseline has no matched recurrence pairs; short windows improve
  recall but increase false positives. Compare frozen controls on held-out
  seeds, retaining half/double-time and short-motif alternatives without labels
  in discovery. Do not promote a feature similarity score into error confidence.
- Qualify low-register denoising separately from quiet-window reduction.
  Captured cleanup improves quiet windows, while active 20–45 Hz mixture energy
  also falls. Test known guitar/fan components, exact frequency collisions,
  attacks and sustain; audition source, pure residue and final masters.
- Keep pitch comparators sparse and experimental. Model range, runtime success
  and short event-duration settings do not establish C1, missing-fundamental,
  distorted-polyphony or legato accuracy. Retain octave, silence and coverage
  failures, and compare fixed decoding choices without intended-note grading.
- Finish portable capture profiles and bounded agent iteration using a fresh
  source/review binding for each take. Keep denoise, tone/dynamics, analysis and
  delivery provenance separate. Every admitted primitive needs a typed hook,
  matching skill and meaningful failure cases.
- The development AUv3 bundle is statically qualified; installation, host
  state, automation, latency and actual Logic playback remain later acceptance.
  Generic editor markers and burned previews do not establish native import.

## Demo decisions and evidence

The reference source is `Movie on 10-5-26 at 3.38 PM.mov` in Documents. Its
read-only FFmpeg 8.1.2 baseline is:

| Measurement | Value |
| --- | ---: |
| Container duration | 150.954 s |
| Video | H.264, 1620×1080, approximately 23.95 fps |
| Audio | Mono AAC, 44.1 kHz, approximately 63 kb/s |
| Integrated loudness | −21.24 LUFS |
| True peak | −4.16 dBTP |
| Loudness range | 4.00 LU |

A standard-library high-frequency onset analysis measured a strong period near
0.678 s in the first 30 seconds. **88.50 BPM**, **177 BPM**, and **44.25 BPM**
are metrical candidates, not confirmed intended tempo. Meter, phrases, and
metronome identity remain unverified. The quiet 4–5 s and 149–150 s windows
are audition candidates, not proven noise-only samples.

The operator subsequently stated that the metronome was approximately **178 BPM**.
The later fitted grid at 88.8007 BPM gives approximately **177.6 BPM** under that
double-time interpretation. Record the former as operator-stated context and
the latter as measured periodicity, retaining alternate interpretations and
limited heuristic confidence. Meter and bar/phrase length are not established
by the tempo statement. The ending includes sweep/tapping legato and further
note subdivisions; sparse pick attacks must not be interpreted as missing notes.

The conservative profile uses a fixed 3 dB FFT denoising reduction with a
−40 dB noise-floor heuristic and no adaptive noise tracking. The bypass and mild6 profiles provide comparisons. The fixed floor does not
derive from a validated noise-only sample. Explicit user-annotated noise
capture is supported when an approved interval is supplied in a profile. Re-measure loudness after all restoration, then normalize and
verify the rendered output. Speech denoisers, automatic de-clipping of intentional
distortion, and speculative note grading are excluded from the demo default.

Rich distortion harmonics, palm mutes, rests, syncopation, sweeps, and tapping
make attack detection and pitch interpretation ambiguous. Note/tone pilots must
evaluate these examples explicitly. Wrong-note claims require an approved
intended-note reference; a distorted chord's strongest spectral peak or estimated
fundamental is insufficient. The operator clarified that the requested mistakes
concern **musical phrases**, not physical signal-phase faults.

Listening acceptance separately evaluates pick attack, palm-mute weight,
sustain, distortion texture, and objectionable noise. Source checks, rendered
artifacts, measured targets, user listening, AU validation, and Logic host
acceptance are separate receipts.

## Agent processing graph and review flags

The ordered graph is **denoise → click/BPM → tonic/mode and repeated-phrase
confidence → recurrence comparison → timestamp/span flags**. Each node records
its source/upstream artifact, parameters, tool version, evidence kind, and
confidence. Agent feedback proposes bounded comparisons and reviewable settings;
reruns retain prior provenance and never silently replace accepted results.

Discovery is automatic: unsupervised musical features, self-similarity, recurrence,
onsets, and rhythmic structure propose phrases, bar groupings, repeated riffs,
and breakdown boundaries without a predeclared intended arrangement. Tonic/mode,
meter, and boundaries can return low-confidence candidates or unknown. Do not
assume four-bar phrases or fixed subdivisions. Distorted low notes, chords,
rests, syncopation, sweeps, tapping, and legato are explicit ambiguity cases.

Internal self-consistency compares recurrent regions for observed timing,
structure, or confidence differences and produces timestamp/span review flags
for starts/ends, skips, rushing, possible missing loops, and unclear riffs. These
flags are hypotheses for audition, not definite mistakes. A user-approved
reference can qualify correctness grading; it is not a gate on automatic
discovery or self-consistency review. Intended-pitch verdicts additionally need
confirmed tuning and an intended-note reference.

The graph/provenance and generic marker CSV support the local graphical review
server, which provides playback, marker filtering and source-bound annotations.
Final Cut/DaVinci Resolve marker imports remain a later development milestone,
with a format spike before any compatibility promise. Marker records retain source-timeline start/end times, label/flag kind,
confidence, review status, and supporting evidence/reference identity. Preserve
the source start offset, actual frame-rate/time-base metadata, and VFR/CFR
identity; define frame rounding and drop-frame timecode explicitly for each
target format. Do not assume this approximately 23.95 fps take is exact 24 fps.
Application import and displayed marker alignment require separate validation.

## October 6–12: 35-hour baseline

Each day budgets five development hours. Each row becomes a Linear ticket with
its stated acceptance evidence; unfinished research is labelled unknown.

| Day | Work | Acceptance |
| --- | --- | --- |
| Oct 6 | Ingestion, CLI, provenance, agent graph | Unicode/space paths, explicit tools, source hashing, isolated runs, versioned API/hooks and ordered graph provenance |
| Oct 7 | Restoration profiles and export | Auditable parameters, post-render loudness/peak checks, preserved rate/channels/timeline, source unchanged |
| Oct 8 | Metronome detection and optional attenuation | Timestamped click candidates, confidence, abstention on overlap, attack-preservation A/B examples |
| Oct 9 | Onsets, calibrated offsets/drift, self-consistency flags; tone/noise pilot | Known-grid tests, timestamp/span review without a reference, optional reference grading, preserved 32 Hz fundamentals |
| Oct 10 | Automatic tonic/mode, meter, phrases/bars/breakdowns; note pilot | Features/recurrence discover candidates without intent, confidence/unknowns, sweep/tapping/legato fixtures, optional reference-qualified note verdicts |
| Oct 11 | Annotations, benchmarks, Quarto | Small labelled corpus, measured comparisons, reproducible report, listening review fields |
| Oct 12 | Hardening, agent/graph integration, handoff | Failure/timeout and MCP/DAG checks, marker-format spike results, reproducible demo and resumable tracker receipts |

Beat This and librosa are comparative rhythm candidates. Default processing must
remain usable without model weights. Automatic discovery and recurrence review
must work without an expected-rhythm file. Definite correctness grading needs an
approved reference and calibrated alignment; onset density alone cannot establish
missed or extra notes, particularly in legato passages.
These additions share the existing five-hour daily budgets; they do not add a
second allocation to the 35-hour baseline. The marker spike may end with an
unverified application import result, which must be recorded as such.

## Additional 35-hour extension

| Lane | Hours | Deliverable |
| --- | ---: | --- |
| Stem experiments | 8 | Optional Demucs six-source benchmark, exact weight provenance, bleed/artifact review |
| Rhythm depth | 8 | Ambiguous-tempo handling, rhythm/intended-note reference alignment, meter/phrase evaluation |
| Robustness | 9 | Broader phone/Photo Booth fixtures, resource limits, interrupted-run recovery, report regression checks |
| Native AU spike | 10 | Swift AUv3 wrapper around bounded Rust DSP; ABI and real-time audit; separate validation and Logic-host receipts |

Stem outputs from a mono mixture are estimates, never recovered original tracks.
Models require an explicit registry entry containing an exact artifact, license,
and expected hash before download. The initial model registry is empty.

The AU spike is future work, not a current plugin. Its render path must not
allocate, block, perform I/O, invoke subprocesses, download models, or unwind
across a native ABI. Offline ML stays outside that path. Installing or repairing
existing plugins, changing host configuration, editing sibling repositories,
and starting host daemons are outside this release.
