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

Rust owns the CLI entrypoint, streaming source hashing, typed run-record
verification and reusable allocation-free biquad/gain DSP. FFmpeg owns
decode/filter/encode and loudness measurement; FFmpeg/ffprobe orchestration
stays in the Python workers that the Rust CLI dispatches (the declared D1
deviation below; S2 correction of the earlier "Rust owns orchestration" text). Bounded Python provides offline
analysis, initially without mandatory model downloads. R/Quarto supplies
reproducible research reports with a plain HTML fallback. Nix and committed
dependency locks define the development environment. `just` is the operator
entrypoint. Zig is deferred until an interoperability or measured performance
need justifies a separate component.

The recipe contract is `doctor`, `demo INPUT`, `clean INPUT PROFILE`,
`analyze INPUT`, `report RUN_DIR`, `export RUN_DIR`, `test`, `check`, and
`model-prefetch MODEL`. The Rust CLI exposes `probe`, `clean`, `demo`, `export`,
`analyze`, and `report`. The Rust CLI natively implements streaming SHA-256 (`hash`)
and typed, metadata-only run-manifest verification (`verify-run`); FFmpeg/ffprobe
orchestration remains owned by the Python workers that the CLI dispatches, a
declared D1 deviation recorded in
`docs/agent-notes/sprints/20261006-s2/rust_core-d1-acceptance.json`. A demo
proceeds through source inspection, clean/export, rhythm analysis, and reporting. Local artifacts are isolated per run under
`artifacts/runs/`; provenance records source identity, commands, tool versions,
profile parameters, analysis resampling, and output measurements.

The current versioned tool/API contract, local MCP stdio adapter, and forty-five
per-tool skills (46 typed tools) expose the same bounded operations. Agent guidance connects research evidence
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
  The frozen generated learned pilot identified C1 correctly in 34/426 eligible
  whole-input frames, with 392 octave errors. A shorter decoder increased sweep
  recall and false positives. The pure evaluator preserves these results and
  the native absence denominator of zero; it supplies no automatic winner.
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
capture is supported when an approved interval is supplied in a profile.
Since S2 (operator decision of October 6, applied in `e697f36`), **FULLER is the
default `clean`/`demo` profile** and refuses with `capture_interval_required`
unless a reviewed per-take `--capture-interval START END --capture-review TEXT`
is supplied; `conservative3` stays explicitly selectable and remains the frozen
default of the MCP `denoise` descriptor. Re-measure loudness after all restoration, then normalize and
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
and expected hash before download. The registry initially was empty; it now
contains the explicitly qualified Basic Pitch ONNX artifact. Its sparse and
generated comparison results remain separate from musical accuracy.

The AU spike is a compiled development scaffold; host validation and a usable
practice plugin remain future work. Its render path must not
allocate, block, perform I/O, invoke subprocesses, download models, or unwind
across a native ABI. Offline ML stays outside that path. Installing or repairing
existing plugins, changing host configuration, editing sibling repositories,
and starting host daemons are outside this release.

## S2 status — October 6, 2026

Dated closeout of sprint S2 (Linear parent TIN-5599; release TIN-5492) against
the rows above. Status words are product states, not tracker states: **done**
means the row's acceptance evidence exists for its stated scope, **partial**
means some acceptance evidence exists and named parts remain, **unknown** means
the claim is unmeasured, and **deferred** means no S2 work was done. Linear
"Done" on a lane child does not upgrade a row. Measurements below come from
the cited receipts; inferences and listening are labelled. The release record is
[RELEASE.md](../agent-notes/sprints/20261006-s2/RELEASE.md), and queued work is in
[S2_FOLLOWUPS.md](sprints/S2_FOLLOWUPS.md).

Integration state: every S2 lane is merged on local `main` at `e3ef39b`. The
last hosted CI run is 37531977858, which succeeded on `1741e33` (1423 Python OK,
106 optional skips, Rust OK, no gitleaks findings). The later merges `4be2812`,
`ebaf72d`, `3e397ad`, `46aee65` and `e3ef39b` had not been pushed and had no
hosted CI run when this was written. The S2 registry had 40 typed tools and 40
skills ([root_admission_e](../agent-notes/sprints/20261006-s2/root_admission_e-receipt.json)).
S3 root integration (2026-10-07, unpushed, no hosted CI) raises it to **42 typed tools and 42
skills** ([root_integration_f](../agent-notes/sprints/20261007-s3/root_integration_f-receipt.json)):
`beat_this_compare` and `guitar_noul_decide` are experimental and currently refuse with a typed
reason (Beat This `final0` is registered hash-bound in `program/models.json` from root's
2026-10-07 fetch, but its Linux runtime is not qualified and no inference has run; guitar_noul
gateway not configured). Web job adapters admitted: `share_export`, `denoise`, `capture_profile` and
`apply_capture_profile` (the last on root's real-worker check from the main checkout,
[root-real-worker-check](../agent-notes/sprints/20261007-s3/root-real-worker-check.json):
synthetic fixture only; listening and real-take web behaviour are not established).
S3 root_admission_g (2026-10-07, unpushed) raises it to **46 typed tools and 45 skills**
([receipt](../agent-notes/sprints/20261007-s3/root_admission_g-receipt.json)): experimental `take_intake`,
`timing_calibration_analyze`, `timing_calibration_apply` (one shared skill) and `stems_estimate` (refuses
`model_not_registered`; no htdemucs_6s registry entry or fetch). No real take has been calibrated or separated.

### Core days

| Day | Status | Evidence | Remaining limits |
| --- | --- | --- | --- |
| D1 Oct 6 ingestion/CLI/provenance | done, with a declared deviation | [D1 acceptance](../agent-notes/sprints/20261006-s2/rust_core-d1-acceptance.json), [rust_core handoff](../agent-notes/sprints/20261006-s2/rust_core-handoff.json) | Rust implements `hash` and metadata-only `verify-run` (`pcm_extent_verified: false`) plus biquad/gain DSP. FFmpeg orchestration owner is `python`. |
| D2 Oct 7 profiles/export | partial | [FULLER A1](../agent-notes/sprints/20261006-s2/fuller_profile-A1.json)/[A2](../agent-notes/sprints/20261006-s2/fuller_profile-A2.json), [root_admission_c](../agent-notes/sprints/20261006-s2/root_admission_c-receipt.json), [share_export fix](../agent-notes/sprints/20261006-s2/share_export_fix-handoff.json), [tone A/B run](../agent-notes/sprints/20261006-s2/tone_ab-20261006T120702Z-actual-run.md) | FULLER is the default and reproduces byte-identically (6/6 WAV stream pairs). The tone A/B is level-matched (0.010 LU), but **the operator's listening preference is not recorded**, so the low-end fullness and thin/nasal feedback stays open. The low-shelf trial was not adopted, and the EQ floor below 160 Hz needs a decision. Noise-only content of the capture interval is unverified. |
| D3 Oct 8 metronome | partial | [rhythm_clicks handoff](../agent-notes/sprints/20261006-s2/rhythm_clicks-handoff.json), [eval results](../agent-notes/sprints/20261006-s2/rhythm_clicks-eval-results.json) | Drift was measured on a sealed synthetic holdout (10/10), and detector delay on 96/96 cells. On the real take: detection only (`attenuation_claim: none_detection_only`), click identity unverified, **capture latency uncalibrated**, no listening A/B. |
| D4 Oct 9 onsets/offsets/flags; tone pilot | partial | [rhythm_clicks real take](../agent-notes/sprints/20261006-s2/rhythm_clicks-real-take.json), [root_admission_d](../agent-notes/sprints/20261006-s2/root_admission_d-receipt.json), [annot_corpus handoff](../agent-notes/sprints/20261006-s2/annot_corpus-handoff.json) | Synthetic phrase timing was within 5 ms on 48/48 sealed phrases. **Per-phrase timing direction on the real take is withheld until calibration** (`withheld_uncalibrated`). Flags triage shows 15 of 171 by default, with 112 navigation proxies. Schema-1 tendency counts in older receipts are uncalibrated. |
| D5 Oct 10 tonic/mode/phrases; note pilot | partial | [phrase results](../agent-notes/sprints/20261006-s2/phrase_anchor_riff-results.md), [real-take spans](../agent-notes/sprints/20261006-s2/phrase_anchor_riff-real-take-spans.json) | Anchor spans give 3 candidate anchors, none adopted. Generated continuous riffs: R1_lag found 12/12 pairs at IoU 0.5 with 79 false positives. **Real-take phrase correctness is unknown until the operator marks at least 10 boundaries.** Meter and tonic/mode stay nullable. **The C1 pitch result of 34/426 stands. No note verdicts are made.** |
| D6 Oct 11 annotations/benchmarks/Quarto | partial | [report bundle build](../agent-notes/sprints/20261006-s2/report_d6-bundle-build.json), [render attempt](../agent-notes/sprints/20261006-s2/report_d6-render-attempt.json), [annot_corpus handoff](../agent-notes/sprints/20261006-s2/annot_corpus-handoff.json) | The hash-bound bundle is verified and the HTML fallback is kept. The first Quarto attempt was blocked: Quarto 1.10.18 sent `syntax-highlighting` to pandoc 3.7.0.2, which rejected it, and the attempt exited 1 after 1172 s. **Update 2026-10-07 (operator ruling):** the report shell now uses the pandoc bundled in the pinned Quarto release (`c162733`). The one approved retry rendered (`demo.html` sha256 `7396e18c…`, [quarto render receipt](../agent-notes/sprints/20261007-s2r/quarto_render-root-receipt.json)). The report has not been read or accepted by the operator. Corpus coverage is 5 of 150.96 s, so P/R is null. The listening-review template is all-null. |
| D7 Oct 12 hardening/integration/handoff | partial | [robustness handoff](../agent-notes/sprints/20261006-s2/robustness-handoff.json), [editor real take](../agent-notes/sprints/20261006-s2/editor_export-real-take-receipt.json), [RELEASE.md](../agent-notes/sprints/20261006-s2/RELEASE.md) | Resume and fixtures pass, and there are 40 tools. **FCPXML/Resolve export exists, but application import is unverified** (`not_performed`; a read-only closeout `ls` found neither Final Cut Pro nor DaVinci Resolve in `/Applications`). The real take stays `calibration_required` (VFR). Hosted CI on the final head is still pending. |

### 35-hour extension and the WEB branch

| Lane | Status | Evidence | Remaining limits |
| --- | --- | --- | --- |
| Stem experiments | deferred | [FOSS audio matrix row 11](../research/FOSS_AUDIO_MATRIX.md) | Demucs code is MIT, but the pretrained weights carry no licence grant, so admission is on hold. No S2 lane ran. Stems from a mono mixture would be estimates. |
| Rhythm depth | partial | [RHYTHM_S2](sprints/RHYTHM_S2.md), [PHRASES_S2](sprints/PHRASES_S2.md) | Drift, ambiguity handling and reference-conditioned anchor spans are in place. **The Beat This comparator was not run.** Intended-note alignment needs a reference that does not exist. Meter is unknown. |
| Robustness | done for its scope | [robustness handoff](../agent-notes/sprints/20261006-s2/robustness-handoff.json), [fixture run](../agent-notes/sprints/20261006-s2/robustness-fixture-run.json) | Resume scenarios 9/9, typed refusals 14/14, fixture pipeline 7/7 runs on P1–P8. The **memory ceiling is unknown** (not measured, no RSS limit). Equivalence with the real take is not established. |
| Native AU spike | partial | [au_auval handoff](../agent-notes/sprints/20261006-s2/au_auval-handoff.json), [AU_AUVAL_S2](sprints/AU_AUVAL_S2.md) | FFI bit parity 150/150, and 0 allocations in 2048 render calls (Rust allocator scope). **The auval discovery stage is `blocked_not_installed`.** Registered render, parameters/state and auval were not performed. **The Logic host check was not performed.** Installation is out of scope. |
| WEB branch | done locally; hosted LATER | [web_reliability handoff](../agent-notes/sprints/20261006-s2/web_reliability-handoff.json), [real web job](../agent-notes/sprints/20261006-s2/web_reliability-real-web-job.json), [web_jobs handoff](../agent-notes/sprints/20261006-s2/web_jobs-handoff.json) | The WEB demo ran: 12/12 API and 13/13 BFF steps, plus 16 failure-injection executions. In the real-take web job, 3621/3621 displayed frames were present, with 0 decode-only output packets and one publication on replay. The `share_export` web_job adapter is admitted (`e3ef39b`). Not done: a hosted or multi-user service, an SLO, and an accessibility audit. Exported clips remain `exported_unreviewed`. |

### Standing evidence boundaries after S2

- No listening acceptance is recorded for any S2 output. Measured loudness
  match, band deltas and packet identity are not listening evidence.
- No missed/extra-note or musical-mistake verdict exists. Phrase and timing
  outputs are review hypotheses with their source timestamps.
- The accepted FULLER run `20261006T041633Z-990aa1bd6737` and the Desktop export
  (`34247a4e…0f10`) were unchanged at release (see RELEASE.md).
- Protected low-register intent still holds: no blanket high-pass, no mains
  notch, and no speech-denoiser default was introduced.
