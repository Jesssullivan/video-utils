# Isolated native gain-automation experiment

This milestone qualifies sample-frame event handling and smooth parameter
handoff beside the existing gain spike. Work is confined to
`native/au-spike/automation/`; the published Rust ABI, Objective-C++ kernel and
Swift scaffold remain unchanged. No parameter tree, extension bundle, installed
plugin, `auval` or Logic acceptance is implied by an isolated processor test.

## Primary-source findings and implementation plan

Apple's current SDK declares `AURenderEvent` as a time-ordered linked list.
Parameter events carry a target, address and ramp duration. A ramp appears only
in its starting render cycle, so the processor must retain its continuation
across blocks. `AUEventSampleTimeImmediate` plus a buffer offset is an allowed
scheduling-input representation. The base `AUAudioUnit.scheduleParameterBlock`
translates it to absolute sample time before delivering events to the subclass
and should not be overridden. The adapter defaults to delivered absolute times;
an explicitly selected scheduling-input mode tests the sentinel conversion.
This avoids silently misclassifying valid negative absolute timestamps. The SDK's native render
block explicitly marks its pull-input block as unsafe-unretained; our earlier
spike independently verified the importance of preserving that ownership.

Implement a standalone native adapter/planner that invokes the existing Rust
gain ABI on prepared scratch data. Reuse the installed tools and ABI library;
do not alter the original gain, kernel or Swift files during the publication
freeze. Use a fixed event batch and fixed scratch/gain buffers, one atomic
mailbox read per nonempty block, and bounded event traversal. Test the actual
Apple event layout through an Objective-C++ conversion shim. No Objective-C
object or block ownership is needed inside these processing functions.

References inspected October 5, 2026:

- [AURenderEvent](https://developer.apple.com/documentation/audiotoolbox/aurenderevent)
  and [AUParameterEvent](https://developer.apple.com/documentation/audiotoolbox/auparameterevent).
- [AUAudioUnit scheduleParameterBlock](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/scheduleparameterblock).
- [Apple custom audio effects](https://developer.apple.com/documentation/avfaudio/creating-custom-audio-effects)
  for the allocation/runtime/I/O boundary.
- Installed macOS SDK `AudioToolbox/AUAudioUnit.h` and
  `AudioToolbox/AUAudioUnitImplementation.h` supplement web documentation that
  required JavaScript. SDK declarations were inspected directly; source is not
  copied into this repository.

## Bounded interface and defaults

- Matching interleaved Float32 mono/stereo, at most 4096 frames; the existing
  planar kernel is not modified or claimed to use this experiment.
- One gain address, `0`, finite linear values in `[0,16]`, at most 32 events per
  block and at most 192000 frames per ramp. The caller owns live event/buffer
  storage and serializes process/configuration calls.
- A fixed batch holds converted events. Read the Apple list without mutation;
  reject unsupported kinds/addresses, reserved fields, cyclic/oversized lists,
  out-of-block offsets and decreasing time order. Equal offsets preserve list
  order. Absolute render times and explicit scheduling-input immediate offsets are supported;
  invalid/past/future events are rejected rather than silently shifted.
- A zero-duration event changes gain on its scheduled frame. A duration `D`
  ramp is continuous at its starting frame and reaches the target at sample
  `start+D`; subsequent blocks continue it. A new event interrupts from the
  current ramp value. This explicit endpoint convention needs actual host
  qualification before any compatibility claim.
- The UI/control handoff uses a lock-free 64-bit latest-value mailbox with a
  sequence and gain bits, one producer and one audio consumer. Read once at
  block start; coalescing intervening edits is intentional. New control targets
  use a 64-frame linear ramp. Scheduled events override that ramp from their
  own sample offset. No retry/spin loop occurs in processing.
  A sequence wraps after 2^32 publications; a consumer missing an entire wrap
  with the same final gain can miss that edit. This is a bounded latest-value
  experiment, not a lossless automation queue or multi-producer API.
- Preflight event metadata, gains and sample multiplication before publishing
  samples or advancing state. Detected errors leave samples and ramp/mailbox
  consumption state unchanged. Scratch work is fixed and allocation-free;
  no clipping, denoising, musical timing edits or sound-quality claim is added.

## Checks and evidence boundaries

Test exact event frames, same-frame ordering, explicit steps, cross-block ramps,
interruption, zero-length blocks and UI smoothing versus an intentional step.
Exercise null/alignment/bounds/nonfinite/overflow input, invalid event types and
addresses, timestamps around signed limits, immediate offsets, cycles, 33-event
lists and reserved fields. Confirm that the Apple list remains byte-identical.

Use a native allocation counter, compiled-object runtime/call inspection and
repeated bounded processing to record observed latency and transition jumps.
Performance is a standalone synthetic measurement; it cannot prove arbitrary
host scheduling, hard realtime deadlines, silence under CPU contention or
listening quality. Build with one job and finite command deadlines using the
existing Apple/Rust tools, with outputs under ignored `.cache/au-automation/`.
Repository code remains MIT; Apple SDK/system-framework terms remain separate.

## Implemented processing boundary

`GainAutomation.cpp` plans scalar gain for each frame, validates a whole block,
and invokes the existing Rust `vu_gain_process` on each frame's one or two
channels in fixed scratch storage. Only after every call succeeds does it copy
samples out and commit the draft ramp/mailbox state. The two member arrays use
49152 bytes regardless of event count. Scalar ABI calls are an experiment;
an eventual gain-envelope Rust ABI could remove per-frame foreign calls after
separate qualification. No such ABI change is part of this milestone.

`AppleEvents.mm` converts borrowed SDK event nodes into a fixed batch. Neither
it nor the core has Objective-C objects, block captures, subprocesses or I/O.
`tests.mm` keeps clocks, output, allocation tracking and producer-thread setup
outside processing. `check.py` performs bounded offline one-job builds, inspects
processing symbols, runs release and Address/UndefinedBehaviorSanitizer fixtures,
and rejects source changes during the check. Its generated receipts remain in
ignored `.cache/au-automation/`.

The independent native audit found and closed a timestamp ambiguity: interpreting
the sentinel's numeric range automatically would corrupt negative absolute
timestamps. Explicit time domains and collision/past-event tests now preserve
Apple's delivered-event contract. One serialized producer is required; native
configuration, process calls and state inspection must remain on the consumer's
serialized lifecycle. Allocation counters cover C++ `new` in the harness;
compiled direct-call inspection and the existing Rust ABI allocation check add
separate evidence, without claiming all host or transitive callees are audited.

## Lane checkpoints

| State | Evidence |
|---|---|
| Primary-source review and durable plan | Observed; October 5, 2026 |
| Isolated planner, Apple event adapter and harness | Implemented and natively compiled |
| Bounded native compilation/behavior/performance receipt | PASS; 2026-10-05T21:37:48.992977+00:00 |
| Existing kernel/Swift gain integration | Not changed |
| AU packaging, parameter tree, `auval`, Logic and listening | Not performed |

The stable `.cache/au-automation/receipt.json` records release and ASan/UBSan
behavior passes, no forbidden direct runtime references in the five processing
symbols, no source-hash drift, and zero counted C++ `new` calls across 1000
`processApple` blocks. Fixtures include maximum-size 4096-frame stereo,
readonly event-list identity, frame-exact step/ramp/interruption, timestamp
collisions/extremes, cyclic/oversized lists, concurrent control publication and
transactional input failures. The UI ramp's measured maximum adjacent jump on
unit input was `0.015625`, versus an intentional step of `1.0`.

For 10000 release blocks of 128 stereo frames, median was 2.375 µs, p95 2.542 µs,
maximum 17186 µs; 6 blocks exceeded the nominal 2666.7 µs budget at 48 kHz.
These observed tails rule out claiming a hard realtime guarantee from this
standalone run. Earlier development runs also observed larger tails. No cause
is inferred from wall-clock timing alone. Sanitizer timings are separate from
release measurements. No listening, host scheduling or AU compatibility was
tested.

Independent read-only native audit accepted the corrected timestamp contract,
all stable source hashes and the untouched earlier spike. Receipt SHA-256:
`7ded23531186c2a685fdc1a81df8b88cf7b68e686800f70fbe10167eb404b340`.
Root can rerun the development check with
`python3 native/au-spike/automation/check.py`; timings and receipt digest will
vary. The check is a development operation, not an audio-tool runtime or an AU
plugin hook.

Authority: operator's ten-hour many-agent goal and root-assigned native lane;
R-HOOK-CONVERGENCE-20261004/R-N11/R-N12/R-N13. No host configuration or plugin
installation occurs in this milestone.
