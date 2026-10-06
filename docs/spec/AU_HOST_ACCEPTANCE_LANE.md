# Next-week AU host acceptance protocol

## Authority, baseline and scope

This is a documentation-only continuation of the operator-approved AU lane under R-HOOK-CONVERGENCE-20261004, R-N12/R-N13. The lane owns only this new document. Baseline is published `c59d7024a9967b920747e07134c6c166c3ddb38d`. Root integrates and publishes; the native audit lane reviews this protocol independently. No build, app launch, plugin copy/install, registry query/write, `auval`, Logic operation, audio device or host configuration change is authorized or performed by this planning task. Commands below are **future protocol data**, not instructions to run now.

The existing product is an experimental **gain-only** AUv3, not an AU restoration plugin. Its container and embedded non-UI extension have been compiled, ad-hoc signed and statically inspected. Direct native/Swift fixtures qualify gain, events and a checked private stopped-state helper. They do not qualify extension loading, DAW automation, ordinary presets, document recall or real-time host deadlines.

Frozen `GuitarGainAudioUnit.swift` exposes `gain`, address0, linear Float32 range0–16/default1, planar mono/stereo, 8000–384000Hz, max4096frames. `fullStateSetterQualified=false`; non-nil `fullState` and `fullStateForDocument` setters set status−100 without restoring. `restoreGainState` is a custom direct-instance helper; an out-of-process AU proxy must not be presumed to expose it. `latency` currently reports0 seconds. `shouldBypassEffect` behavior has no explicit source implementation qualification.

## Evidence order and completion rules

| Stage | Evidence sufficient for that stage | What it cannot establish |
| --- | --- | --- |
| 0 source/local checks | Source commit, locked tools, native behavior/ARC audits, hash-bound signed bundle | Discovery, runtime or musical restoration |
| 1 approved installation | Exact artifact copied to a reviewed destination; post-copy inventory/hash/signature checks | Registered component or runnable extension |
| 2 discovery | Targeted PlugInKit match plus AudioComponent identity/version/provenance | Successful factory/host render; a `+` election is not a render pass |
| 3 registered extension render | Async out-of-process instantiation and deterministic offline registered-AU fixtures | Logic compatibility, hardware deadlines or saved sessions |
| 4 parameters/state | Standard public API/control/event tests; actual dictionary and DAW recall round trips | Private direct-instance helper alone cannot satisfy this stage |
| 5 AU validator | Targeted auval exit/status/transcript tied to the exact registered artifact | UI quality, sample-accurate musical results or Logic acceptance |
| 6 Logic | Owned disposable project, AU3 manager evidence, insert/render/automation/state/latency observations | Other Logic/OS/architecture versions, all hosts or restoration quality |

Record each stage as pass/fail/blocked/not-performed independently. `auval` and Logic recall may expose existing source gaps; a discovery or rendering pass must survive as its own result while full host acceptance remains incomplete. No aggregate "AU works" claim until every required stage, including state and bypass policy, passes for the stated environment. Transient gain-only experimentation may be reported explicitly as such, without saved-session reliability.

## Stage 0 — make the candidate reviewable before activation

Next week's root first assigns exact source ownership for the state/bypass changes and host harness. Existing files remain frozen until that release. Resolve generic state restore before promising preset/project recall: inspect the real superclass dictionary, establish a bounded public dictionary/canonical private-gain contract, and test all validation before mutation. Do not decode or guess Apple's observed opaque `data` bytes. If superclass consistency or an alternative subclass-owned serialization contract cannot be proved, retain the current rejection and mark state acceptance blocked.

Stopped/quiesced restore requires a single serialized lifecycle owner, stale revision/token rejection and compatible schema/address/ranges. A host may recall while rendering: rejection is safe but not feature acceptance. Any active-recall support needs a separate bounded control-to-render transaction design, never main-thread waits, render locks, dictionary decoding in the callback or asynchronous half-restored parameter state. Do not assume Logic will always stop rendering for recall. Verify nil/no-op, malformed/incompatible payloads, coherent target reads and the parameter provider's agreement after a successful restore. Ramp progress and stream format are not persisted musical state.

Declare the bypass contract separately: host insert bypass and AU `shouldBypassEffect` need independent tests. If implementing native bypass, define raw input preservation, event/control progression and transitions before code; no hidden latency or sudden undefined state. Current source is not a bypass pass.

Rebuild via existing developer recipes only when source changes justify it:

```bash
just au-spike-check
just au-automation-check
just au-state-check
just au-package-check
just au-package-plan
just au-package-build
```

These are existing local developer checks, not activation commands. Record exact commit, source hashes, artifact receipt, arm64 slice, minOS26/SDK27, nested bundle IDs, component `aufx`/`vuGn`/`Jess` version65536, license resources, signed entitlements and system-library dependencies. Prototype IDs are not an allocated vendor namespace or collision proof. Source changes require a new artifact receipt and independent review, not reuse of the old binary hash.

Use current ad-hoc signing for the bounded local experiment. The existing build explicitly signs the extension before the container with the exact sandbox-only entitlement file and verifies the outer bundle with `--strict --deep`; do not sign with `--deep`. No Developer ID identity, team, certificate access, notarization or public distribution is implied. If local loading rejects this identity, preserve the error and prepare a reviewed signing change; do not disable Gatekeeper, remove quarantine, relax sandbox entitlements or borrow credentials. Any Developer ID distribution candidate needs a separate reviewed certificate/hardened-runtime/notarization plan and new artifact identity.

## Stages 1–2 — concrete future copy and discovery

The proposed exact destination is `/Applications/VideoUtilsGainPrototype.app`, with embedded extension `/Applications/VideoUtilsGainPrototype.app/Contents/PlugIns/VideoUtilsGain.appex`. Apple documents AUv3 containing apps in Applications; this is not an AUv2 `.component` install. System-location permissions must be resolved within the future approved action; no automatic `sudo` or alternate destination. A different destination requires updating the concrete proposal first.

Before asking for that future approval, root provides the actual candidate bundle hash/inventory/signatures, destination, installation/discovery/launch commands and known state/bypass limitations. Approval must explicitly cover installation, containing-app launch and targeted extension/host validation, with Logic/device interaction separated if needed. This planning task asks for no approval and performs no dependent action.

After that authorization, capture the targeted pre-install inventory using a future bounded host harness that enumerates only exact `AudioComponentDescription(aufx,vuGn,Jess)` via `AVAudioUnitComponentManager.components(matching:)`, plus this query:

```bash
/usr/bin/pluginkit -m -A -D -v -i org.video-utils.gain.prototype.audio-unit
```

The match includes all versions/duplicates. An existing destination, same bundle ID at another path or matching component from another product halts the copy until ownership/collision is resolved. Do not overwrite, uninstall, re-elect or silently select another developer's component.

The proposed copy/signature commands, **only after approved absent-target and ownership checks**, are:

```bash
/usr/bin/ditto --rsrc --extattr \
  /Users/jess/git/video-utils/.cache/au-packaging/VideoUtilsGainPrototype.app \
  /Applications/VideoUtilsGainPrototype.app
/usr/bin/codesign --verify --strict --deep /Applications/VideoUtilsGainPrototype.app
/usr/bin/codesign --display --verbose=4 /Applications/VideoUtilsGainPrototype.app
/usr/bin/codesign --display --entitlements :- \
  /Applications/VideoUtilsGainPrototype.app/Contents/PlugIns/VideoUtilsGain.appex
```

Verify post-copy bytes, nested inventory, no symlinks, identifiers, entitlements and signatures against the approved artifact before any launch. Copy preserves existing signatures; signing at the destination is not an automatic repair. Installation/discovery can update the automatic registry already; do not claim that the copy stage leaves registry state unchanged.

If the copy is intact, the approved containing-app action is:

```bash
/usr/bin/open -n /Applications/VideoUtilsGainPrototype.app
```

Record launch success and actual window evidence independently; close only the operator-approved owned app normally. Capture the same filtered PlugInKit query and component enumeration afterward. No `pluginkit -a/-r/-e`, manual `lsregister`, AudioUnit cache deletion, reboot, host preference rewrite or unrelated plugin scan is part of this protocol. Missing discovery remains a recorded failure; investigate source/package/signing evidence before proposing any additional intervention.

Component enumeration must show exactly one eligible intended identity/version and preserve ambiguity if duplicates remain. Record the discovered bundle ID/path as supplied by the target APIs/metadata. Registry rows and names alone cannot cryptographically identify executing code; bind them to the copied signatures, observed process/bundle provenance where available, and the registered-AU fixtures. Do not assert a provenance field that the target API does not actually provide.

## Stage 3 — registered-AU rendering without audio hardware

Build the future small Swift host harness in a separate owned lane and independently review it before activation. No such harness exists yet. It must use asynchronous `AUAudioUnit.instantiate(with:options:completionHandler:)` with `.loadOutOfProcess`, retain the returned unit and never block the main thread awaiting completion. Prefer the executable extension's supported out-of-process path; there is no qualified in-process framework to force-load. Capture requested/observed instantiation mode, errors, startup time and available process/bundle provenance, not a guessed concrete Swift subclass identity on a remote proxy. SDK instantiation options are requests that may fall back: an ambiguous/unavailable observed mode is unknown and cannot pass the specifically out-of-process claim merely because that flag was requested. Preserve any narrower registered-render evidence separately.

Use the returned standard AU's public `renderBlock` and `scheduleParameterBlock` with synthetic pull buffers and a bounded monotonic sample clock. Do not construct `GuitarGainAudioUnit` directly and relabel that result "registered extension". AVAudioEngine offline manual rendering is an additional integration fixture: Apple states its offline input/output nodes are disconnected from audio hardware. A graph-level result must record any mixer/conversion effects separately from the unit's own samples.

Preallocate inputs, outputs and event fixtures on the control side; write receipts/audio only after rendering. The callback has no file writes, logging, models, Python, subprocesses or control-thread synchronization. Instantiation deadline10 seconds per attempt, at most3 attempts; fixture deadline120 seconds; max4096frames/block, max32events/block, max192000rampframes. Resource timeout signals only that harness's identity-checked live process group; no `killall`, extension-daemon signalling or host cleanup. Record startup, processing and teardown as separate timing categories.

Fixture matrix: mono/stereo at44.1/48/96kHz; blocks64/128/256/512/4096; zero-frame and valid non-divisible final blocks. Feed silence, distinct L/R impulses,32.703Hz sine, distinct stereo tones and a seeded low-level broadband signal. Constant gains0/0.5/1/2/16 must produce finite independent per-channel `input×gain`; set each target while resources are released, then allocate and compare from the first frame so UI smoothing does not contaminate this oracle. Use amplitude0.01 for high-gain fixtures. Compare with an independent Float32 oracle, max absolute error≤2e−6 for these bounded synthetic values and zero sample-offset tolerance for an isolated impulse. Unity establishes gain-only low-frequency preservation, not fan cleanup.

Exercise repeated allocation/render/deallocation, block-boundary control updates and fresh-instance reset. Native error/null/overflow rollback and retained-block lifetime remain mandatory direct-native regression cases: foreign/invalid pointers must not be injected through a live IPC/DAW interface. A registered proxy cannot be expected to expose private error-status/helpers. Unsupported format tests use valid public format objects and preserve the returned errors.

## Stage 4 — parameter and state qualification

The public tree must retain one readable/writable/rampable linear gain parameter, identifier/address/range/default as above. Query provider and parameter values after delivery; do not equate the current ramp multiplier with its target. Test settled0.5/1/2, rapid edits and repeated same-target edits without ramp restart. Measure public AUParameter behavior for invalid/out-of-range values separately from direct native rejection; do not assume Apple clamps17 to16. Obtain the base scheduling block once outside rendering; no tree mutations/client-observer installation inside render.

At48kHz with128-frame blocks, use constant Float32 input0.01 and a stopped/pre-allocation initial gain1. Schedule a duration0 step to0.5 at absolute frame37; that frame immediately uses0.5. Schedule a256-frame ramp to2 at frame61; only a ramp's start sample retains its previous gain0.5. Interrupt it at frame173 with a64-frame ramp to0.25: the independent uninterrupted first ramp would have gain1.15625 at173, which the second ramp starts from, reaching0.25 at237. In a separate fresh gain1 instance, schedule the immediate scheduling-input duration0 step to0.75 with offset17 at sample-clock0; frame17 immediately uses0.75. Confirm source sample times, scheduled offsets and measured output transitions with the independent oracle; each non-interrupted ramp reaches its target at start+duration under the existing engine's declared convention. Decode delivered absolute timestamps using the published adapter; do not pass scheduling-input sentinels to its absolute-time parser. Compare at equivalent absolute frames across different block partitions. Client observer notification timing is not proof of sample accuracy.

UI changes use a64-frame control ramp: measure exactly where its first consumed block begins and whether it continues after a same-value edit. This control smoothing is not audio lookahead. Read provider target from non-render code. Concurrent host controls must preserve finite/ranged values and eventual latest consumed target; mailbox coalescing is deliberate and must not be sold as a lossless UI-event queue. Preserve the native31-bit ticket wrap/ABA limitation in stress findings.

State checks distinguish these three paths:

| Path | Required proof / present limitation |
| --- | --- |
| Private direct-instance helper | Existing32byte canonical schema/address/ABI/range checks, stopped ownership, stale revision/token rejection and first-frame restored gain; not DAW recall |
| Standard registered-AU fullState/document API | Save at gain0.5, change to2, stop/quiesce where supported, restore exact dictionary and restart: parameter/provider/private payload/output all agree0.5; nil/no-op, malformed/cross-version rejection and no partial mutation; current bundle rejects non-nil and cannot pass |
| Logic preset/project | Fresh owned preset save/change/recall, project save/close/reopen with gain and automation, instance duplication and two instances holding distinct targets; includes host-driven recall timing; untested until observed |

Opaque superclass data and the32byte private payload must agree in any accepted getter/restore contract. Bound dictionary shape and size before native mutation, preserve compatible metadata and record version migration policy. In-process custom helper calls do not substitute for standard remote state. Active recall, host seek/restart and interrupted-ramp reset semantics need an explicit source contract before adding them to the accepted matrix. Current frozen bundle's restore rejection is an expected recorded limitation, not a passing state test.

## Stage 5 — targeted Apple validator

Only after discovery and registered fixtures, and within the approved validation action:

```bash
/usr/bin/auval -v aufx vuGn Jess
```

Capture executable/tool/OS/architecture versions, exact stdout/stderr, exit status and named failed subtests, tied to copied artifact identity and current discovery rows. Run one bounded120second attempt; a hang/failure remains failure, not a reason to re-elect/cache-reset/continue-until-green. Read available options for the then-installed tool before proposing additional flags; the protocol does not assume an undocumented strict mode. Apple describes validation as API/basic-functionality testing, not DSP/audio-quality or UI proof. If the installed validator cannot exercise this AUv3 path, record unsupported/incomplete and qualify the registered harness separately; do not substitute a direct-instance pass.

## Stage 6 — Logic, bypass and latency

After specific authorization for Logic launch, owned project writes and audio-device interaction, record actual Logic/macOS/build versions and native/Rosetta mode. Use a new disposable project under ignored `.cache/au-host-acceptance/`, never the musician's working project. Keep monitoring/record input disabled; retain the existing device configuration unless an exact change was approved. Logic may open its configured device even for a planned offline bounce, so device permission is not inferred from prior hardware-free fixtures.

In Logic's Plug-in Manager, capture the exact product/version and `(AU3)` classification, validation result and activation state. Insert on owned mono/stereo audio tracks; capture generic gain UI/default/range. Render unity and0.5/2 gain with level-matched synthetic clips and offline bounce; document normalization, dither, channel mapping, pan/mixer gains, project rate and region timing. Compare source/bounce samples after accounting for declared container/graph conversion, not by interpreting the knob screenshot as a sound result. Then inspect the operator's copied guitar take at unity/controlled gain only; no denoise/mastering claim follows.

Record track automation events/readback, playback/loop/restart behavior and bounce transition frames. Logic may transform automation into its own segment/ramp representation; exact scheduled-harness sample accuracy is a separate fact. Document differences rather than automatically blaming the player or declaring a host failure. Test host insert bypass and standard AU bypass as separate paths; check output gain, ramp policy and restoration on toggling. Saved preset/project recall must pass Stage4's DAW round trip before session reliability is accepted.

Measure four distinct quantities:

| Quantity | Method and report |
| --- | --- |
| Algorithmic audio latency | Read AU latency; unity impulse input/output sample alignment across block sizes/rates; current expected0 samples. Report format/mixer alignment separately |
| Control response |64frame UI smoothing ≈1.333ms at48kHz plus time until host delivers the next block; event ramp duration is deliberate parameter interpolation, not audio latency |
| Processing/IPC duration | Monotonic timing around registered render calls, plus core timing only where separately instrumented; warmup100 then10000 release blocks/configuration, capped workload; median/p95/p99/max and every budget exceedance, errors, pauses, CPU/power/thermal environment |
| Host/device end-to-end | Logic offline bounce offsets versus actual monitored/device round-trip; hardware/loopback requires separately approved setup and cannot be inferred from AU latency0 or offline wall-clock timing |

At48kHz deadlines are1.333/2.667/5.333/10.667ms for64/128/256/512frames, respectively. Count observed call durations exceeding the corresponding block budget, and report host underrun/dropout indicators if the host exposes them. An offline call is not a scheduled realtime callback. Existing standalone128frame measurements already had6/10000 wall-clock exceedances and a17186µs maximum; no hard realtime guarantee exists. Any observed underrun or unexplained tail fails the tested operating envelope until investigated. Zero observed overruns in a bounded run supports only that run; it proves no universal hard deadline. Do not instrument file/console/ARC allocation from inside the release render path to obtain these measurements.

## Future architecture: offline restoration and native realtime primitives

Keep the current hash-bound CLI/MCP/skill graph responsible for FFmpeg decode/export, captured fan denoising, click analysis, BPM/meter/pitch/phrase estimates, model inference and marked-video/report production. Python/librosa/ONNX/model downloads stay in bounded offline jobs, with user-selected source, model/profile hashes, uncertainty and independent listening evidence. Rendered clips and musical review markers import into Logic through ordinary files; a gain plugin does not identify rushed notes.

Rust remains the shared numerical core for portable bounded primitives. Swift exposes AU parameters/lifecycle and native Objective-C++ bridges preallocated buffers/events/state. Candidate future realtime blocks include gain, bounded EQ/dynamics and a separately benchmarked native spectral denoiser; each needs preservation tests near32Hz, pick attacks, saturated texture and sustain, a stated fixed processing delay and a separate source/host qualification. No blanket high-pass, noise gate or speech-model default. No algorithm is admitted simply because an offline library produced useful audio.

Control-plane decisions and state serialization run off the callback. If a future companion requests analysis, trigger it explicitly from user/control context with bounded jobs and cancellation; never start processes, access files, load weights or invoke Python from a callback. Loading preset tables/models and allocating FFT/window/scratch storage occurs before rendering; render sees only validated immutable/preallocated state and a bounded parameter/event handoff. Replacing state requires an explicit safe ownership/retirement design; lock-free does not mean wait-free. New app-group/security-scoped/XPC entitlements would be a separate reviewed architecture change; the present sandbox-only bundle has no granted file/IPC restoration workflow.

## One-week allocation and durable deliverables

| Day |5–10hours/day focus | Exit evidence |
| --- | --- | --- |
| 1 | Standard state/bypass contract, primary SDK review, exact ownership release, independent negative tests | Proved source contract or explicit bounded state blocker; no activation |
| 2 | Implement state/bypass fixes and registered-host harness; native regression/ASan/UBSan/object review | Hash-bound revised candidate and reviewed future host harness |
| 3 | Packaging/signing regression, collision/provenance proposal, concrete approval; approved copy/discovery if granted | Approved action receipt plus copied-artifact/discovery evidence, or review-ready pending activation |
| 4 | Registered out-of-process offline render/parameter fixtures; targeted validator after authorization | Independent numeric matrix and validator transcript with preserved failures |
| 5 | Owned Logic project, generic UI/automation/bypass and preset/document recall after authorization | Actual version-specific Logic results; state gaps remain gaps |
| 6 | Timing/load/rate/block matrix and32Hz guitar unity/gain comparisons; investigate tails | Tested operating envelope, latency categories and bounded evidence |
| 7 | Regressions, review, durable receipts/tracker, next native restoration primitive design | Private published source, replayable acceptance packet, explicit unverified list |

Budget35–70hours total. Source/state/harness work can continue without activation authorization; later host-dependent stages wait for actual authorization rather than inferring it from elapsed time. If state or host behavior needs more work, preserve a gain-only experiment and reserve remaining hours for diagnosis instead of promising denoising-plugin delivery. Root owns every factual Linear update.

Each future stage writes a source-bound receipt under `docs/agent-notes/` and private raw artifacts under ignored `.cache/au-host-acceptance/`: source commit/hashes, candidate and copied artifact identity, exact authorized scope/action, OS/SDK/tool/Logic versions, identifiers/path/provenance, commands/API calls, inputs/settings, expected-versus-observed samples/state, timing aggregates, errors, and independent-review result. Redact unrelated plugin/project/device identifiers; never publish the original musician's recording. R-N11 timeout actions use `actor | target/ownership | reason | ruling | prior_state | result`. Removal/rollback is a separately concrete owned-target action, not automatic registry repair; recorded prior state and exact installed ownership must be checked before any removal.

## Primary references and review checkpoint

- [Apple: Work with Audio Units in Logic Pro](https://support.apple.com/guide/logicpro/lgcp22a0dab0/mac): AUv3 Applications location, AU3 Plug-in Manager classification and host behavior.
- [Apple: Performing offline audio processing](https://developer.apple.com/documentation/avfaudio/performing-offline-audio-processing): offline manual rendering disconnects hardware input/output.
- [Apple: AUAudioUnit asynchronous instantiation](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/instantiate(with:options:completionhandler:)), plus installed `AUAudioUnit.h:363–380` and `AudioComponent.h`: async/no-main-thread-wait and out-of-process options.
- [Apple: AU latency](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/latency), installed `AUAudioUnit.h:960–978`: processing impulse delay differs from wall-clock/device/control delay.
- [Apple: fullState](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/fullstate), [fullStateForDocument](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/fullstatefordocument) and [parameter scheduling](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/scheduleparameterblock): public state/event contracts, not the project's private helper.
- [Apple: AU development/validation](https://developer.apple.com/library/archive/documentation/MusicAudio/Conceptual/AudioUnitProgrammingGuide/AudioUnitDevelopmentFundamentals/AudioUnitDevelopmentFundamentals.html): validator scope only; old AUv2 packaging passages do not define this AUv3 package. Installed `/usr/share/man/man1/auval.1` and `/usr/share/man/man8/pluginkit.8` were read as documentation, not executed.

Planning checkpoint: nearest repo AGENTS read; published candidate, native/Swift limits, existing recipes and primary contracts inspected read-only. No activation or runtime result generated. Independent audit accepted the corrected protocol after resolving constant-gain setup, explicit step/ramp targets and observed-execution-mode findings; no remaining must-fix. Its owned receipt is `docs/agent-notes/2026-10-05-au-host-acceptance-review.md`. Acceptance covers this protocol only, not host runtime.
