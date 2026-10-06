# Repository-only AUv3 packaging prototype

Authority: operator-approved full-force AU packaging lane; R-HOOK-CONVERGENCE-20261004, R-N12/R-N13. Baseline is `eb378bd33e6c1ab408245e58f93430a495efbf6b`. This lane owns only new `native/au-spike/packaging/**`, this plan and its dated receipt. Published kernel, Swift AU, automation, state and Rust sources stay frozen.

## Plan and definition of done

1. Specify stable component and bundle identifiers, a non-UI factory and a containing application. Record the SDK/template basis before compilation.
2. Commit a bounded Python developer build tool with a dry-run target manifest. Compile only hash-bound isolated source copies into ignored `.cache/au-packaging/`; one Cargo/Swift job, installed macOS SDK, finite per-command timeout, no dependency installation.
3. Build a native arm64 macOS 26.0 application containing one `.appex`, using `_NSExtensionMain` as its extension executable entry. Both targets receive only the app-sandbox entitlement. Sign explicitly inside-out with ad-hoc identity; inspect metadata, signatures, linkage, symbols and nested layout without loading either binary.
4. Independently review the source and receipt. Preserve separate states for bundle compiled, signatures locally checked, extension runtime, registered AU validation and Logic acceptance.

The build uses compiler/linker commands directly rather than `xcodebuild`, whose target build graph can include Launch Services registration. The target graph and artifact layout are a manual prototype, not an Xcode project, notarized distribution or template-generated release package. A later Xcode project must preserve this source provenance and be inspected for registration side effects before use.

## Target contract

| Target | Contract |
| --- | --- |
| Container | `VideoUtilsGainPrototype.app`, `org.video-utils.gain.prototype`, executable `VideoUtilsGainPrototype`, package `APPL`, minimal AppKit informational window; build/inspect only |
| Embedded extension | `Contents/PlugIns/VideoUtilsGain.appex`, `org.video-utils.gain.prototype.audio-unit`, executable `VideoUtilsGain`, package `XPC!` |
| Extension point | `com.apple.AudioUnit`; principal Objective-C runtime class `VideoUtilsGainFactory`, `NSObject` conforming to `AUAudioUnitFactory`; no storyboard/editor |
| Component | type `aufx`, subtype `vuGn`, manufacturer `Jess`, component version `65536` (1.0.0); local prototype identity, not an allocated vendor code or registry collision proof |
| Dependencies | Existing MIT Rust gain ABI and published Objective-C++/Swift AU sources, compiled from isolated copies; Apple system frameworks and C++/Swift runtime; no embedded third-party dynamic library |
| Entitlements | `com.apple.security.app-sandbox = true` only, for each target; no microphone, network, file access, app-group or host permissions |
| License resources | Exact hash-bound root MIT `LICENSE` copied into each target's `Contents/Resources/LICENSE` before signing |
| Toolchain | Existing Rust 1.95.0 and selected Xcode macOS 27 SDK, native arm64 with macOS 26.0 deployment target; no earlier OS/Intel compatibility claim |

The factory validates the supplied type/subtype/manufacturer before creating the AU. Gain is the existing address-0 linear parameter in [0,16], mono/stereo planar Float32, max 4096 frames, sample-accurate host events and UI smoothing already qualified by direct-instance checks. Packaging adds no DSP or restoration algorithm.

Generic `fullState`/`fullStateForDocument` setters remain **unqualified and reject non-nil input**. The existing checked private stopped-state helper remains unchanged. Bundle packaging is not preset persistence qualification.

## Boundaries and checks

Allowed actions: write named source files, clone the exact required source subset into this lane's ignored cache, offline single-job compilers, plist validation, Mach-O/static symbol inspection and `codesign` signing/verification of owned artifacts. No app/extension launch, dynamic bundle load, `pluginkit`, `lsregister`, `open`, `auval`, plugin folder write, host configuration, audio device or Logic operation. A receipt records commands actually invoked rather than claiming a globally unchanged registry without sampling it.

Dry-run and build validate exactly one component, four-character identifiers, nested bundle identifiers, no storyboard/principal ambiguity, minimal entitlements, bounded deployment target and source-path safety. Artifact inspection must reject symlinks, external/non-system dynamic linkage, mismatched executable architectures or component metadata, missing factory/AU/Rust ABI symbols and invalid nested signatures. Source hashes are checked again after compilation; any drift fails the result.

Before any later activation, root must present the concrete reviewed bundle and the exact proposed host action for user approval. Installation and runtime are outside this lane's current authorization.

## Primary basis

- [Apple AUAudioUnitFactory](https://developer.apple.com/documentation/audiotoolbox/auaudiounitfactory) and installed macOS SDK `AUAudioUnitImplementation.h:448–476`: non-UI principal classes derive from NSObject and implement the factory protocol.
- [Apple Audio Unit app extensions](https://developer.apple.com/library/archive/documentation/General/Conceptual/ExtensibilityPG/AudioUnit.html): a no-UI extension uses `com.apple.AudioUnit`, a principal class and `AudioComponents` metadata.
- Installed Xcode `Audio Unit Extension.xctemplate/_NonUISpecific/Common/AudioUnitFactory/AudioUnitFactory.swift`: NSObject factory and empty `beginRequest(with:)` template; this lane writes original minimal code rather than copying Apple template source.
- Installed SDK `Foundation.framework/Foundation.tbd` exports `_NSExtensionMain`; extension main is linked, not executed.

## Checkpoint

2026-10-05: Design recorded before compilation. Five contract tests pass. The final ignored receipt at `.cache/au-packaging/receipt.json`, created `2026-10-06T00:06:19.900916+00:00`, has SHA256 `9b0b1f487f1aa45ba3cb405a75fa296fcad6865e5c7783b32fd52b17dd0746b0` and status `bundle_compiled_signed_inspected_not_activated`. Both thin ARM64 executable targets validate minOS26/SDK27, system-only dynamic dependencies, sandbox-only ad-hoc signatures, exact eight-file layout and unchanged source hashes. Source and artifact review are separate from activation; no executable was launched or loaded. See the dated implementation receipt and independent packaging audit for final qualification.
