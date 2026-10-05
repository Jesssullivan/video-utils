# Research decisions and limitations

Primary sources reviewed October 5, 2026. Choices below distinguish usable local
capabilities from optional experiments. See the project specification for demo
measurements and the dated implementation note for delivery evidence.

## Restoration and mastering

[FFmpeg's filter documentation](https://ffmpeg.org/ffmpeg-filters.html#afftdn)
documents FFT noise reduction, explicit noise-profile capture, noise tracking,
and noise-only output. Its
[loudnorm documentation](https://ffmpeg.org/ffmpeg-filters.html#loudnorm)
supports measured two-pass normalization and notes that dynamic processing
upsamples internally; output sample rate must be set explicitly. The initial
conservative profile uses fixed `nr=3`, `nf=-40`, with adaptive tracking disabled.
That floor is a heuristic. Band limiting is a separate audition alternative.
Post-filter measurements determine normalization; a source scan is insufficient.
`adeclick` is available but is not automatically applied to guitar attacks.
`arnndn` is documented for speech and is excluded from the guitar default.

[Audacity's noise-reduction manual](https://www.audacityteam.org/manual/effects/noise-removal-and-repair/noise-reduction/)
requires a noise-only profile and recommends inspecting removed material. We
adopt that review paradigm: select an explicitly annotated noise sample, compare
at matched loudness, and listen for wanted guitar in the residue. Quietness alone
does not establish that a window is free of clicks, sustain, or room reflections.

[libspecbleach](https://github.com/lucianodato/libspecbleach) is a native C spectral
denoising candidate under LGPL-2.1. It is optional and not embedded in the initial
Rust core. Compare its artifacts and real-time suitability before integration.
[FFmpeg's own licensing page](https://ffmpeg.org/legal.html) explains that the
effective license depends on enabled components. Record the actual build rather
than assigning a blanket license to every FFmpeg binary.

**Decision:** use the already available FFmpeg path for today's candidate.
Noise removal is bounded and reversible; destructive guitar reshaping requires
listening evidence. No improvement claim follows from a louder output alone.
The user's downtuned nine-string reaches approximately 32 Hz. An 80 Hz high-pass
is unsuitable as a default here; apparent low-frequency noise may be wanted
fundamental, and distortion harmonics/palm mutes are part of the intended tone.

## Rhythm, metronome, and performance

[librosa's documented beat tracker](https://librosa.org/doc/0.10.2/generated/librosa.beat.beat_track.html)
uses onset strength, tempo estimation, and dynamic programming. It offers a
transparent offline baseline; this linked documentation is version-specific,
not a declaration of the project's installed version. The
[upstream license](https://github.com/librosa/librosa/blob/main/LICENSE.md) is ISC.

[Beat This](https://github.com/CPJKU/beat_this) provides beat/downbeat inference
and optional pretrained models. Upstream explicitly releases its code and
published model weights under MIT while distinguishing training-data rights.
It is an optional comparison, not an installed or validated capability here.
Download qualification remains tied to the exact chosen checkpoint and hash.

**Decision:** compare classical onset/periodicity analysis with learned
beat/downbeat inference on labelled examples. Report half/double-time candidates,
timestamps, latency calibration, and uncertainty. A metronome detector must
distinguish click transients from guitar pick attacks and abstain when overlap
makes that distinction unreliable. Attenuation is opt-in and needs a residue/A/B
review. Beat estimates alone cannot establish intended meter, missing notes,
extra notes, or the start of a musical phrase.

Note/tone pilots must include sweeps, tapping, syncopation, rests, distorted
chords, and palm mutes. Agent tuning exposes parameter proposals and comparative
results through the versioned tool contract; intended-note correctness requires
a supplied reference. Spectral peaks alone cannot grade distorted guitar notes.

## Source separation

The [officially maintained Demucs successor](https://github.com/adefossez/demucs)
identifies itself as the maintenance home and cautions that new feature work is
limited. Demucs is MIT-licensed; its experimental `htdemucs_6s` adds guitar and
piano sources, with documented quality limitations. Registry review must still
record the selected weight artifact's provenance and license.

**Decision:** keep six-source Demucs in the optional eight-hour extension.
Measure bleed and transient/sustain damage on this mono phone mixture. Call
outputs estimated stems. A speech denoiser or a generic separator is not evidence
of transparent distorted-guitar restoration.

## Native AU and repair boundaries

[Apple's AUAudioUnit documentation](https://developer.apple.com/documentation/AudioToolbox/AUAudioUnit)
defines the AUv3 subclass and render interface. The intended extension is a
native Swift wrapper calling a narrow Rust DSP ABI; offline FFmpeg/Python/ML
workers remain outside the render callback.
[Apple's validation guidance](https://developer.apple.com/library/archive/documentation/MusicAudio/Conceptual/AudioUnitProgrammingGuide/AudioUnitDevelopmentFundamentals/AudioUnitDevelopmentFundamentals.html)
describes `auval` checks and explicitly separates them from DSP-quality testing.
Passing validation is therefore separate from successful Logic hosting and
musical listening acceptance.

**Decision:** no AU implementation or installed-plugin repair is claimed today.
Future diagnosis starts with observed component identity, architecture, signing,
validation output, and host evidence. Cache removal, rescanning, installation,
or changes to another plugin need a separately authorized target and receipt.

## Qualification state

`program/models.json` intentionally registers zero models. No checkpoint has
been downloaded and hash-qualified for this project. Research candidates are
not recipe guarantees. Plain HTML reporting can carry today's measurements;
R/Quarto sources support a richer optional research report.
