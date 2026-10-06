# video-utils repository contract

## Mission and authority

Local-first restoration and rhythm analysis of guitar recordings in phone and
Photo Booth videos. The operator-approved October 5, 2026 plan is recorded in
`docs/spec/PROJECT.md`. Rust owns the CLI and reusable DSP; FFmpeg owns media
decoding/export; bounded Python owns offline analysis; R/Quarto owns research
reports. Swift AUv3 is a later integration, never an implicit runtime claim.

User instructions and the nearest repository overlay take precedence. Global
authority is R-HOOK-CONVERGENCE-20261004 (TIN-3692 comment
98cf680c-7299-4949-bfb2-60079053ad43): R-N11 requires target ownership/live-session
checks before signalling; R-N12 makes hooks advisory; R-N13 requires traceable
receipts, durable notes here, and factual tracker evidence. Do not edit sibling
repositories, terminate other sessions, or change host/plugin configuration as
part of this project.

## Product axioms

Build for technical-guitar woodshedding, practice and clear communication among
working bands. A take should become a shareable restored clip with source-timed
musical review data and reproducible processing evidence. Evaluate changes by
their effect on that practice workflow and the unusual distorted nine-string
instrument, rather than by a generic speech-cleanup or studio-mastering score.

1. Technical/virtuoso detection must account for riffs, irregular subdivisions,
   palm mutes, rests, tapping, sweeps and legato. Musical phrase and timing review
   work without a predefined score; correctness claims need sufficient intent
   and calibrated evidence. Attack counts alone never identify missed notes.
2. Agent participation is part of the product: every processing primitive has
   a typed MCP hook and skill stating intent, knobs, dependencies, research,
   iteration and evidence. Preserve comparisons, sparse coverage, uncertainty
   and failures so agents and musicians can assess a proposed setting.
3. Heavy distortion and unusual low tuning shape all processing and benchmarks.
   Protect approximately 32 Hz musical content, low-string weight, saturated
   texture, pick transients and sustain; compare fan cleanup, dynamics and EQ
   with the recorded instrument context and listening feedback.

Clip delivery combines restored audio/video and useful phrase/rhythm review;
optional stems remain estimates with source provenance. The underserved-market
assertion is a product hypothesis: cite dated primary comparisons, acknowledge
overlapping features, and retain unverified specialized accuracy as unknown.

## Work and interfaces

- `just` is the operator entrypoint. Root `justfile` routes `just/*.just`.
- Commit toolchain/dependency locks; model downloads are explicit and hash-bound.
- Original recordings, rendered media, model checkpoints, and caches stay out
  of Git. The repository is private; privacy still applies to CI/log artifacts.
- Preserve source rate/channels and timeline in masters. Analysis resampling is
  separate and recorded. Never overwrite the input.
- Keep workers bounded; use existing approved builders for heavy compilation,
  and cluster placement for GPU work after checking capacity. No new host daemon.
- Contributors own named files; root integrates and publishes. Parallel research
  and implementation lanes are authorized by the operator for this project.
- Verify behavior with meaningful synthetic fixtures and the actual demo.

## Evidence and acceptance

Measurements, inferences, and unverified listening claims must be distinct.
Never describe a mono-mixture estimate as a recovered original stem. Do not
label missed/extra notes without an approved expected-rhythm reference. BPM,
meter, phrase boundaries and onset confidence may be unknown.

Save research with primary-source links and limitations in `docs/research/`;
specifications in `docs/spec/`; dated run/implementation receipts in
`docs/agent-notes/`. Keep `program/linear.json` synchronized with published
project/issue IDs. Source checks, rendered demo, listening acceptance, AU
validation and actual Logic host acceptance are separate states.

AU render code must not allocate, block, invoke subprocesses, perform I/O,
download models, or unwind across a native ABI. Plugin installation and repairs
are outside this release's scope.

## Instrument and agent processing graph

The instrument is always a nine-string down-tuned guitar used for deathcore,
technical and virtuoso playing, with intentional fundamentals near 32 Hz.
Protect that low end; no blanket 80 Hz high-pass, mains notch or speech-denoiser
default. Palm mutes, rests, tuplets, tapping and sweeps are musical context.

The operator's constant tuning is lowest→highest C F Bb Eb Bb Eb Ab C F.
`program/instrument.json` records strings 9→1 as C1 F1 Bb1 Eb2 Bb2 Eb3 Ab3 C4 F4
with MIDI 24,29,34,39,46,51,56,60,65. Pitch classes are operator-stated;
octaves are inferred from the approximately 32 Hz low string, high F above
standard E4, and ascending order. A4=440 equal-temperament frequencies are
theoretical, not measured. Preserve the supplied Eb2→Bb2 interval and the
entire custom tuning. This context is not identified played notes or an
intended-note reference; do not silently substitute a standard/all-fourths tuning.

The operator means musical phrase mistakes. Analyze a hash-bound graph: denoise
then click/BPM, pitch/tonic/mode evidence (nullable), phrase recurrence, and
review flags carrying source timestamps or spans. Every tool has a typed MCP
hook and a repository skill under `.agents/skills/`; agents inspect, research,
compare supported knobs and record evidence. Intended notes require tuning and
a reference; note correctness cannot follow from a dominant spectral peak.
Generic markers are an interchange pilot; Final Cut/Resolve import requires
actual application proof in a future milestone.

For the demo's reference-aware branch, use `program/demo-arrangement.json` and
its verbatim operator prompt in `docs/agent-notes/`. Expected phrase lengths and
the 404-click total are intent, not observed counts. Keep the automatic baseline
available; bind comparisons to the exact source and analyzed input. Preserve the
approximate first-phrase anchor, second-chorus inheritance and uncertain breakdown
execution. Property tests must exercise timing changes, missing/extra boundaries,
ambiguity and partial coverage without forcing detections to match the reference.
The first five seconds include setup guitar/amp sounds and possible mechanical
windup; they are not blanket authorization for a pure-noise training interval.

## Constant recording and tone context

`program/capture-context.json` records the operator's large-box-fan background
and artist references: Lorna Shore, The Haunted, Meshuggah, Kublai Khan TX,
Mgła and Children of Bodom. Treat these as persistent project context. Preserve
low-string weight, string separation, pick attacks, saturated texture, sustain,
tapping and legato. Studio/full-band spectra do not establish the guitar's
isolated spectrum, microphone response, expected score or an automatic EQ curve.

Noise capture must bind the current source and reviewed opening interval;
apply a measured captured profile to the complete take when requested. Fan
frequency, microphone position and noise level require per-take measurements.
Do not assume mains/blade lines or apply a notch that overlaps musical notes.
Compare stronger denoising, controlled compression and bounded EQ reversibly,
with matched presentation level and explicit residue/artifact review. Keep pure
denoising separate from tone/dynamics processing and reanalyze changed inputs.

Treat tonal balance, dynamics and delivery mastering as explicit graph stages.
The operator's current audition feedback is insufficient low-end fullness and
thin/nasal balance; cleanup measurements alone do not close that feedback.
Capture-response references need their own provenance and level matching.
Do not claim that EQ recreates an uncaptured fundamental or the in-room amp tone.
Every analysis declares the signal version it consumed; invalidate downstream
results when that input changes. Shareable overlays default to compact section/
phrase labels, BPM and brief issue badges. User-reported issues retain their
authorship and must remain distinguishable from detector hypotheses.
