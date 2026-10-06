# Mastering and capture response: primary-source review

Reviewed October 6, 2026 by `/root/mastering_future`; R-N13. Purpose: support
the [future balance design](../spec/future/MASTERING_AND_CAPTURE_RESPONSE.md)
for distorted nine-string C1 guitar and reported thin/nasal processed tone.
This is a dated upstream/API review, not a local install, quality audition,
new DSP benchmark or host acceptance. Current `Cargo.toml` has no dependencies;
none of the candidate libraries below is thereby present in the product.

## Existing offline engine and optional filters

[FFmpeg equalizer](https://ffmpeg.org/ffmpeg-filters.html#equalizer) documents
peaking gain/frequency/width controls. [Bass/lowshelf](https://ffmpeg.org/ffmpeg-filters.html#bass_002c-lowshelf)
provides shelving with gain, frequency, width and processing options. Reverse
IIR block processing introduces block-sized delay. [Acompressor](https://ffmpeg.org/ffmpeg-filters.html#acompressor)
exposes threshold, ratio, attack/release, detection/linking and mix.
[Loudnorm](https://ffmpeg.org/ffmpeg-filters.html#loudnorm) supports linear/dynamic
and one/two-pass normalization; dynamic true-peak processing upsamples internally
to 192 kHz, requiring explicit output rate.
[Alimiter](https://ffmpeg.org/ffmpeg-filters.html#alimiter) uses lookahead,
provides latency compensation/tail flushing and defaults to automatic output
leveling. These are upstream capabilities, not current exposed tools.

The repository's captured-profile worker currently exposes peaking EQ only,
with a 160 Hz lower bound. It keeps forward IIR, fixed 25% compression mix and
separate pure denoise/residue. This distinction comes from local source and the
[refinement contract](../spec/RESTORATION_REFINEMENT_LANE.md), not upstream
documentation. Consequently a 32 Hz bell or a shelf is a future schema/DSP
extension, while the specified FULLER-v1 body candidate fits today's limits.

Use pinned FFmpeg 8.1.2 source alongside live docs:
[biquads](https://github.com/FFmpeg/FFmpeg/blob/n8.1.2/libavfilter/af_biquads.c),
[limiter](https://github.com/FFmpeg/FFmpeg/blob/n8.1.2/libavfilter/af_alimiter.c).
Implementation and configured-binary licensing must be recorded before adopting
another filter/build. Current engine licensing and negative-control speech
denoisers remain in [the FOSS matrix](FOSS_AUDIO_MATRIX.md).

Engineering decision: retain the existing FFmpeg path for an immediate bounded
EQ comparison. Do not add a new limiter merely to call the output mastered;
measure delivery loudness/peak, native extent and tails first. Extra gain can
increase fan audibility, force later attenuation and conceal prior bass removal.
No automatic high-pass, mains notch, clipping repair or synthetic sub-bass is
appropriate without specific source/intent evidence.

## Optional reusable DSP and independent plugin comparator

| Candidate / primary evidence | Dated capability and licensing | Proposed use and limits |
| --- | --- | --- |
| [biquad-rs](https://github.com/korken89/biquad-rs), [manifest](https://github.com/korken89/biquad-rs/blob/master/Cargo.toml) | Inspected master declares 0.6.0, MIT OR Apache-2.0. `no_std`, DF1 and DF2T, generic float coefficient/state types, per-sample `run`. | Small Rust EQ candidate. Pin exact package/commit and transitive lock before use; test low-frequency response, finite state, automation and cancellation of invalid coefficients. `no_std` alone does not prove real-time behavior or safe retuning. |
| [FunDSP](https://github.com/SamiPerttu/fundsp), [manifest](https://github.com/SamiPerttu/fundsp/blob/master/Cargo.toml) | Inspected master declares 0.23.0, MIT OR Apache-2.0. Static `AudioNode` and dynamic `AudioUnit`; `tick`/`process`; analytic response for linear networks; `allocate` prepares node buffers. Default features include file/FFT facilities. | Broader Rust graph/prototyping comparator, only if composition earns its dependency footprint. Disable unnecessary features and preallocate outside render; verify selected nodes rather than asserting the whole library allocates nothing. Upstream `AudioUnit` trait is unrelated to Apple AU registration. |
| [LSP parametric EQ manual](https://lsp-plug.in/?page=manuals&section=para_equalizer_x8_mono), [project COPYING](https://github.com/lsp-plugins/lsp-plugins/blob/master/COPYING) | Manual provides bell/shelf modes, input/output controls, band inspection and before/after spectrum. IIR versus FIR/FFT choices have different phase/latency; project COPYING contains GPLv3, while selected modules/dependencies need separate inventory. | Optional independent audition/UI reference. Band inspection is useful for finding a reported nasal region. Do not copy a generic guitar high-pass recommendation or claim the product's native AU acceptance from this plugin. No installation or runtime availability asserted. |

Choice: prefer a narrowly bounded biquad primitive if reusable Rust EQ is the
next implementation need; compare actual coefficient/response/automation behavior
before selection. FunDSP is a research option, not a necessary framework
migration. LSP is an optional manual comparator, not a server/worker dependency.
Library/package licenses do not grant rights to third-party IRs, amp models,
artist recordings or reference clips. No new model or copyrighted reference
audio is required for the first comparison.

## Reference and validation limits

The causal source→denoise comparison identifies a change to captured mixture,
not the room instrument's original spectrum. Unknown microphone/capture AGC,
room nulls and clipped/absent signal prevent unique inverse reconstruction.
This is the design's engineering inference; none of the linked filter APIs
promises authentic tone recovery. Record paired simultaneous capture if the
operator wants a reference-assisted response estimate. Regularize gain, show
coverage/coherence and retain missing lows as missing; use recording guidance
when no reliable estimate exists.

Use native 44.1 kHz mono waveform/clock evidence for the actual demo, while
analysis resampling remains explicit. Existing band averaging and sparse
attack panels are descriptive. A 160 Hz bell can add perceived body through
harmonics and nearby captured content; it is not evidence of a C1 fundamental
restoration. Musical attacks, fan and metronome can overlap in every measured
band. Inspect residue and gain-matched source/pure-denoise/processed/encoded
delivery with the operator before adopting a tone.

Primary-source URLs were opened during this lane. Live master/docs are dated
snapshots; pin and reread exact selected releases before implementation. No
install, dependency/host/configuration change, audio render or new actual
measurement was performed.
