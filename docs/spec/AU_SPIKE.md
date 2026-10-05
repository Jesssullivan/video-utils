# Native AUv3 gain spike

This lane builds a small native bridge around the existing Rust gain DSP. Its
purpose is to qualify ABI and render-lifecycle behavior without installing a
plugin or changing Logic, audio routing, host configuration, or signing state.
An offline restoration pipeline is not a realtime Audio Unit.

## Durable plan and constraints

1. Keep all native work in `native/au-spike/`; reuse the root `video-utils`
   library without changing its sources. Publish an isolated Rust static library
   with a versioned C header, bounded sample count, explicit status codes and
   documented pointer ownership. No model/runtime dependencies or downloads.
2. Put the actual render callback in Objective-C++ rather than Swift. Prepare
   fixed scratch buffers outside rendering. The callback accepts mono/stereo
   noninterleaved Float32, pulls input, invokes Rust gain and copies successful
   results. It must reject incompatible buffers, oversized blocks and unsupported
   render events rather than silently applying the wrong behavior.
3. Add a Swift `AUAudioUnit` scaffold with input/output buses and explicit
   resource allocation/deallocation. This is source/native compile evidence;
   containing app, extension registration, editor, parameter automation,
   signatures, installation and Logic host qualification are separate work.
4. Check null/alignment/size/finite/overflow ABI behavior, buffer preservation
   on errors, resource lifecycle and the callback's allocation behavior using
   bounded native harnesses. Compile only these small sources with the already
   installed Rust and Apple toolchains, one Cargo job and finite subprocess
   deadlines. Generated artifacts remain under ignored `.cache/au-spike/`.

The repository is MIT licensed. This spike introduces no JUCE, NIH-plug, CLAP
wrapper, proprietary binary or third-party framework source. Apple system
frameworks and SDK tools retain their own terms. Apple SDK availability is a
Darwin prerequisite; Nix does not replace the Apple SDK or provide signing
identity. The inspected environment has Rust 1.95.0 and Apple Swift 6.4 on arm64
macOS 26. No toolchain installation is part of this lane. The managed local-build
hook is advisory under R-N12; respect bounded resource use and retain command
receipts rather than treating its diagnostics as approval gates.

## Interface and realtime boundary

The C ABI carries only raw Float32 buffers, lengths, a finite linear gain and
integer status/version values. The caller retains buffers and guarantees valid,
aligned storage and exclusive mutable access for the call. Null and bounds
checks cannot prove that an arbitrary foreign address points to live memory.
No Rust object layout or Rust unwinding crosses the ABI. Gain preserves signal
shape and is not denoising, mastering, low-frequency reconstruction or limiting.

Native rendering must not allocate, lock, log, do I/O, invoke Python/FFmpeg,
download a model, or send Swift/Objective-C messages. Resource allocation and
format/state changes happen while rendering is stopped. A future parameter
surface needs smoothing, sample-accurate event handling and independently tested
state recall; those capabilities must not be inferred from a gain prototype.

## Primary references

- [Apple custom audio effect sample](https://developer.apple.com/documentation/avfaudio/creating-custom-audio-effects)
  describes separation of Swift UI and native DSP and prohibits allocation,
  file I/O, locks and runtime interaction during rendering.
- [AUAudioUnit internal render block](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/internalrenderblock)
  and [render resource allocation](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/allocaterenderresources())
  define separate rendering and lifecycle surfaces. Local SDK headers supplement
  the online documentation where the documentation renderer is unavailable.
- [Rust FFI and unwinding](https://doc.rust-lang.org/nomicon/ffi.html#ffi-and-unwinding)
  describes foreign buffer ownership and ABI unwind boundaries.
- [Apple Audio Unit validation](https://developer.apple.com/library/archive/documentation/MusicAudio/Conceptual/AudioUnitProgrammingGuide/AudioUnitDevelopmentFundamentals/AudioUnitDevelopmentFundamentals.html)
  separates `auval` API/basic render validation from editor and audio quality.

Sources inspected October 5, 2026. These references establish interface rules;
they do not establish that this project's plugin loads or sounds correct.

## Lane checkpoints

| Evidence state | Current status |
|---|---|
| Durable plan and installed toolchain inspection | Observed; October 5, 2026 |
| Rust C ABI source and harness | Pending |
| Native render kernel and Swift scaffold | Pending |
| Bounded native compilation and behavioral tests | Pending |
| AU extension bundle, signing and registration | Not performed |
| `auval` validation | Not performed |
| Logic insertion, automation and save/reopen | Not performed |
| Listening acceptance or realtime restoration ML | Not performed |

No installation, plugin repair, component registration or host mutation is
authorized implicitly by running this spike's checks.
