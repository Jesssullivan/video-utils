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
| Rust C ABI source and harness | Implemented; three Rust tests and the compiled C harness passed |
| Native render kernel and Swift scaffold | Implemented and compiled with the installed Apple toolchain |
| Bounded native compilation and behavioral tests | Passed after libc++ linkage and ARC correction; three Rust tests, C ABI harness, native callback harness, compiled render-body audit and direct Swift object lifecycle |
| AU extension bundle, signing and registration | Not performed |
| `auval` validation | Not performed |
| Logic insertion, automation and save/reopen | Not performed |
| Listening acceptance or realtime restoration ML | Not performed |

No installation, plugin repair, component registration or host mutation is
authorized implicitly by running this spike's checks.

First bounded check at 2026-10-05 20:57 UTC used one Cargo job, offline locked
dependencies and the installed SDK. It passed ABI validation and 1024 native
render calls with zero counted C++ `operator new` calls; the Rust allocator
counter separately recorded zero allocations across 1024 gain calls. Swift
linking initially lacked libc++; explicit linkage fixed the next bounded check.
The counters cover these exercised code paths, not every
allocation API or arbitrary host behavior.

The corrected check at **2026-10-05 20:58 UTC** passed native linking and direct
Swift object construction/resource allocation/deallocation at 48 kHz stereo and
44.1 kHz mono. Mismatched channel configurations were rejected. C/ABI tests cover
null, misalignment, maximum lengths, nonfinite gain/samples and overflow without
partial mutation. Native callback checks cover pre-allocation/post-release calls,
wrong bus, oversized blocks, undersized buffers, unsupported events, nonfinite
input, null output-buffer adoption and retained-block lifetime. No audio device
or registered component was used by these harnesses.

Independent compiled-code review found that the initial Objective-C++ callback
and helper retained their pull-input block parameters through ARC. Their source
contained no explicit message calls, but the object code invoked
`objc_storeStrong`. Both render-side parameters now use `__unsafe_unretained`;
the host owns the pull block for the invocation. Compiled callback inspection is
required alongside the allocation counters before claiming the callback avoids
Objective-C runtime entry. Getter/block construction and destruction occur
outside rendering and still use normal ownership.

At **2026-10-05 21:03 UTC**, the corrected source passed all native checks and
the compiled render-body audit. Independent read-only review of both complete
disassembly bodies confirmed no Objective-C/Block runtime references and closed
the ARC finding. The automated check fails if either expected body is absent or
contains runtime references; it does not claim to audit every transitive callee
or a foreign host's pull callback.

Reproduce with `python3 native/au-spike/check.py`. The checker uses installed
toolchains, one Cargo/Swift job, offline locked dependencies and 120-second command
deadlines. It records source hashes, command arguments, tool versions and exact
evidence states in ignored `.cache/au-spike/receipt.json`; generated binaries and
Swift module caches are kept beside that receipt. It never installs or registers
an AU. Current gain is fixed at unity in the Swift scaffold; kernel gain changes
are exercised by the native harness, without advertising a host parameter tree.
No UI, gain smoothing, parameter events, state serialization, containing app,
extension metadata, universal build, Developer ID signature or installer ships
in this spike.

Each command runs in a new owned process group. A deadline expiry checks the
actual group identity and live child before stopping only this invocation's
compiler/harness descendants, under R-N11; it never signals a shared build or
another session. Failed checks retain their diagnostic receipt with the
command and deadline failure rather than promoting native acceptance.

| Actor | Target/ownership | Reason | Ruling | Prior state | Result |
|---|---|---|---|---|---|
| AU implementation lane | Owned `native/au-spike/` and ignored build artifacts | Qualify an isolated native bridge using bounded installed tools | Operator request; R-N12 advisory hooks and R-N13 durability | Source scaffold; first Swift link lacked libc++ | Native compilation and harnesses passed; AU/Logic acceptance remains unperformed |
