# AUv3 extension packaging: primary-source verification

Date: 2026-10-05. Actor: `/root/clip_baseline/plugin_sources`, reattached by root.
Authority: operator-approved parallel AU packaging lane; repository contract;
R-HOOK-CONVERGENCE-20261004, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`, R-N12/R-N13.
Ownership: this new dated note only. Inspection was read-only apart from writing
this note. No compiler, bundle load, registration, application launch, signing,
plugin installation, device operation or host configuration was performed here.

## Findings

The proposed no-UI AUv3 principal-class design agrees with the installed SDK and
current Xcode template. Packaging is distinct from discovery, registration,
component validation and actual Logic processing. The selected local toolchain
is **Xcode 27.0, build 27A266a, macOS SDK 27.0 (`macosx27.0`)**, read from
`/Applications/Xcode.app/Contents/version.plist` and the selected SDK's
`SDKSettings.plist`. Earlier lane text calling this the macOS 26 SDK needs
correction. A **26.0 deployment target** remains an independent design choice;
these reads do not prove runtime compatibility on macOS 26.

`xcrun --show-sdk-path` returned
`/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk`.
SDK paths below are relative to that directory. Template paths are relative to
`/Applications/Xcode.app/Contents/Developer/Library/Xcode/Templates/`.

| Inspected local authority | Relevant evidence | SHA-256 |
| --- | --- | --- |
| `System/Library/Frameworks/AudioToolbox.framework/Versions/A/Headers/AUAudioUnit.h` | Lines 318–331 distinguish AUv2 C factories from AUv3 extension factories | `f471a799bbe5c508d6aff8fedea6a6090026f077dbc2042f64c30dfc29016308` |
| `System/Library/Frameworks/AudioToolbox.framework/Versions/A/Headers/AUAudioUnitImplementation.h` | Lines 451–471 define non-UI NSObject factory, protocol inheritance and creation method | `1a79cfc180da2444029f3f486a8d014b24d25cd6c137ac51977f403c9beb96c1` |
| `System/Library/Frameworks/AudioToolbox.framework/Versions/A/Headers/AudioComponent.h` | Lines 22–102 document AUv2 component scanning, C factory and sandbox flag | `adf3d4d2dd3903b781da98c9c0c7125857dfb124e61915ad5e299be10f2eb6d8` |
| `Project Templates/MultiPlatform/Application Extension/Audio Unit Extension.xctemplate/TemplateInfo.plist` | No-UI option defines nested metadata and principal class without `factoryFunction` | `246b253f8d436f0976fc6f311680df57f156e5753c1f236ade4ccc14e12ed2a4` |

## Factory and metadata contract

- **AUv3:** app extension with an `AUAudioUnitFactory` principal class that
  creates an `AUAudioUnit` subclass. A no-UI factory derives from `NSObject`;
  the protocol inherits `NSExtensionRequestHandling`. The installed no-UI Swift
  template implements an empty `beginRequest(with:)` plus
  `createAudioUnit(with:)`. Apple documents that the host supplies a generic UI
  when the AU has no custom editor. [Factory API](https://developer.apple.com/documentation/audiotoolbox/auaudiounitfactory),
  [AUAudioUnit registration forms](https://developer.apple.com/documentation/audiotoolbox/auaudiounit).
- **AUv2:** `.component` metadata refers to an
  `AudioComponentFactoryFunction`; `AudioComponentRegister` is another AUv2
  registration route. Neither route substitutes for this AUv3 factory.
  The SDK's legacy component-directory scan description must not be treated
  as the install procedure for an embedded `.appex`.
- The no-UI template places `AudioComponents` under
  `NSExtension.NSExtensionAttributes`, with
  `NSExtensionPointIdentifier = com.apple.AudioUnit` and a principal-class
  string. Its component dictionary has description, manufacturer, name,
  sandboxSafe, subtype, tags, type and integer version; **no factoryFunction**.
  The UI template does include that key, so the finding is specific to the
  selected no-UI path rather than a prohibition for every AUv3 variant.
- `NSExtensionPrincipalClass` names the runtime class. The template uses a
  module-qualified Swift class. The proposed explicit
  `@objc(VideoUtilsGainFactory)` supplies an intentional unqualified Objective-C
  runtime name; static symbol inspection must verify it. No storyboard is
  needed for this no-UI extension. [Extension-key hierarchy](https://developer.apple.com/library/archive/documentation/General/Reference/InfoPlistKeyReference/Articles/AppExtensionKeys.html).

The project's `aufx` / `vuGn` / `Jess` values are four ASCII characters; SDK
`AudioComponent.h` accepts four-character ASCII strings for the corresponding
OSType fields. They are local prototype identities, not an allocation or
collision-check result. The stable component identity and integer version must
agree between plist, factory guard and AU constructor. Apple's AU-specific
guide confirms `com.apple.AudioUnit` for a no-UI extension and describes the
component keys. [AU app-extension guide](https://developer.apple.com/library/archive/documentation/General/Conceptual/ExtensibilityPG/AudioUnit.html).

## Nested layout, linkage and signing

Apple identifies `Contents/PlugIns` as the standard location for embedded
extensions and recommends signing nested code first, then its containing app.
Separate explicit signing is preferable to recursive repair-style signing.
That supports the proposed
`VideoUtilsGainPrototype.app/Contents/PlugIns/VideoUtilsGain.appex` layout.
Signature verification establishes structural/signature evidence only.
[Apple TN2206](https://developer.apple.com/library/archive/technotes/tn2206/).

Apple's sample separates app, extension and shared DSP framework targets.
It supports separating interface/factory code from the DSP kernel; it does not
require this prototype to ship its Rust kernel as a dynamic framework.
Static Rust and Objective-C++ objects in the extension are a project choice.
Inspect the resulting Mach-O dependencies for host-specific paths and any
unintended third-party dylibs. Any shared dynamic framework must use
extension-safe APIs and an appropriate Frameworks location.
[Current AU sample](https://developer.apple.com/documentation/avfaudio/creating-custom-audio-effects),
[embedded-framework rules](https://developer.apple.com/library/archive/documentation/General/Conceptual/ExtensibilityPG/ExtensionScenarios.html).

The installed multiplatform extension-base template specifies macOS runpaths
`@executable_path/../Frameworks` and
`@executable_path/../../../../Frameworks`. These matter if a future package
introduces embedded dynamic frameworks; the current static-kernel proposal
should not invent such a dependency.

The selected Foundation SDK stub exports `_NSExtensionMain` at
`System/Library/Frameworks/Foundation.framework/Versions/C/Foundation.tbd:38271`.
This supports link feasibility for the proposed extension executable entry.
The bounded Foundation-header search found no public declaration of that entry;
an exported linker symbol is **not a documented manual-build API guarantee**.
The handwritten compiler graph must remain labelled a local packaging
prototype pending actual extension loading, not a template-equivalent release.

## Sandbox and discovery boundaries

`sandboxSafe` component metadata describes eligibility for loading in a
sandboxed process; it is not the same thing as the signed
`com.apple.security.app-sandbox` entitlement. The minimal gain-only design
uses host buffers and needs no microphone, network, user-selected file,
app-group or resource-usage exceptions. Keeping only app-sandbox on each
target is a **needs-based prototype decision**, not a claim that every Xcode
template uses exactly that entitlement list. The archived general extension
guide describes broader template defaults.

Apple documents signing both container and extension, using the same signing
approach during testing. Ad-hoc signing is test packaging evidence; it is not
Developer ID, notarization or App Store distribution acceptance. The guide
also distinguishes Xcode debugging registration and user installation/approval
from merely producing files. Its older OS/architecture statements must not be
substituted for proof on the installed 27.0 SDK or the chosen arm64 target.
[Extension creation, signing and distribution](https://developer.apple.com/library/archive/documentation/General/Conceptual/ExtensibilityPG/ExtensionCreation.html).

This lane intentionally performed no `pluginkit`, `lsregister`, `open`,
`auval`, dynamic bundle load or Logic operation. A concrete bundle may therefore
pass static inspection while host discovery remains **unknown**. Do not infer
that the machine's registry is globally unchanged without sampling it; the
claim here is limited to the commands this actor invoked. Before activation,
root presents the reviewed artifact and the exact proposed host action for
operator approval under the lane plan.

## Verification and communication receipt

Current Apple documentation endpoints returned JavaScript shells through the
web reader. Their linked `.md` representations were retrieved in memory with
Python `urllib.request` from the same Apple domain; no sample archives or SDK
content were downloaded to disk. Archived Apple guides and installed headers
and templates supplied independent structural evidence. No Apple template
source was copied into project implementation.

Sent the factory/plist distinctions to AU owner and independent auditor, and
sent the discovered **SDK 27 versus deployment 26** distinction to AU owner and
root. This note changes no frozen Rust, Objective-C++, Swift AU, parameter,
state, automation or packaging source. It qualifies source/design evidence,
not compiled-artifact inspection, loaded extension behavior, preset acceptance,
restoration fidelity or actual Logic host acceptance.

Read-only inspection of the subsequently supplied `packaging/build.py` and
`targets.json` confirmed the source expresses the nested metadata above,
arm64/deployment 26.0, explicit Objective-C runtime principal name, single
app-sandbox entitlement, Swift `-application-extension`, Objective-C++
`-fapplication-extension`, and linker reference to `_NSExtensionMain`.
No build was invoked by this actor. The completed note contains eight direct
Apple primary-source links, checked structurally; executable behavior remains
the AU owner's and independent auditor's separate evidence lane.

## Appendix: staged host acceptance requirements

Root reattached this reviewer for a **documentation-only** host-acceptance
review. The packaging owner's dated receipt now records compilation, ad-hoc
signing and static inspection of the concrete bundle, while explicitly leaving
activation unperformed. This appendix reads that receipt and the frozen Swift
wrapper; it neither reproduces compilation nor upgrades the owner's artifact
checks to runtime evidence. The following checklist is a proposed acceptance
contract for an independently authorized future host session.

| Stage | Required evidence and claim boundary |
| --- | --- |
| Approval and artifact identity | Bind the reviewed app/extension hashes, identifiers, signature receipt and actual proposed installation/discovery action before user approval. Rebuilds require fresh identities. Preserve current SDK 27/deployment 26/arm64 limits. |
| Registered discovery | Query exactly `aufx` / `vuGn` / `Jess`, with zero component flags/mask unless deliberately testing flags. Record matching component count, name, version and origin metadata if available; no match or multiple matches is a diagnostic requiring review. Files existing in `.cache` do not establish registration. |
| Factory and extension load | Asynchronously instantiate the discovered component without blocking the main thread. Record success/error and lifecycle evidence from the extension-backed path. A direct `GuitarGainAudioUnit` constructor or process-local `registerSubclass` harness does not exercise app-extension discovery/factory/entry. |
| Process placement | macOS AUv3 defaults to out-of-process. Record actual placement if observable; do not silently infer it from requested options. Apple reserves in-process loading for appropriately packaged plugins. The current executable-only extension has no separately qualified in-process framework path. |
| No-UI controls | Confirm the host exposes a generic gain control, stable address 0, range [0,16], default 1 and meaningful read/write values. No custom editor is promised. A missing custom view is consistent with this no-UI design; generic-control availability remains actual host evidence. |
| Rendering and lifecycle | Exercise the published mono/stereo planar Float32 contract, supported block sizes through 4096, resource allocation/deallocation and restart. Compare gain output against known source samples and record actual rate/channels, errors, dropout observations and latency. Host realtime deadlines require host observations, not standalone timing extrapolation. |
| Automation | Qualify ordinary control edits and scheduled host playback separately. Test frame-local steps, cross-block ramps, interruption, same-frame ordering and host parameter readback. Then record/replay a bounded Logic automation gesture as its own host result; GUI slider movement alone is not sample-accurate automation proof. |
| Bypass | Distinguish host insert bypass from AU `shouldBypassEffect`. The latter promises unprocessed input-to-output routing. The inspected Swift wrapper has no explicit bypass override; establish actual behavior with a known signal rather than inferring either mode from gain=1 or from host UI state. |
| State and reload | Standard `fullState` / `fullStateForDocument` setters remain unqualified and reject non-nil input with project status -100. Their current getters or private stopped-state helper do not establish normal host preset/project restore. Treat preset recall, project reopen and independent-instance restore as expected limitations until separately fixed and qualified. |
| Acceptance receipt | Record component validator result, extension load, measured gain/automation, generic UI, bypass, state limitations and actual Logic result as separate states, including host/OS/version/architecture. No restoration, nine-string tone preservation or listening acceptance follows from this gain-only package. |

Apple's current host sample searches **registered** components through
`AVAudioUnitComponentManager.components(matching:)`, asynchronously creates
the selected AU, and explains default macOS AUv3 process placement. This is
the discovery/load basis; it does not grant this lane permission to register
the package. [Hosting sample](https://developer.apple.com/documentation/audiotoolbox/incorporating-audio-effects-and-instruments),
[asynchronous AU creation](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/instantiate(with:options:completionhandler:)).

Apple's factory API explicitly places generic controls with the host when an
AU supplies no custom interface. Externally generated parameter changes reach
`implementorValueObserver`; `implementorValueProvider` returns the current
value when the parameter tree needs refreshing. The wrapper connects both
callbacks to the kernel, but this source wiring is not host readback proof.
[Factory/no-UI contract](https://developer.apple.com/documentation/audiotoolbox/auaudiounitfactory),
[value-change callback](https://developer.apple.com/documentation/audiotoolbox/auparameternode/implementorvalueobserver),
[value-refresh callback](https://developer.apple.com/documentation/audiotoolbox/auparameternode/implementorvalueprovider).

Apple supplies `scheduleParameterBlock` in the base AU class and directs
subclasses not to override it. SDK `AUAudioUnit.h:160–179,495–509` specifies
parameter addresses, rampability, sample times and event targets; the host
caches the scheduling block before rendering. SDK
`AUAudioUnitImplementation.h:190–203` specifies time-ordered render events and
requires continuation of ramps beyond their starting render cycle. The
qualified standalone planner's endpoint and bounded event policies still need
the actual host path to verify them.
[Scheduling API](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/scheduleparameterblock),
[render-event representation](https://developer.apple.com/documentation/audiotoolbox/aurenderevent),
[bypass property](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/shouldbypasseffect).

Apple distinguishes preset state from document state. `fullState` captures
parameter/custom-property state but excludes transient stream formats;
`fullStateForDocument` covers document-specific state and falls back to
`fullState` when not implemented. The current wrapper's
`fullStateSetterQualified = false` and setters at lines 52–72 are a concrete
reason to leave conventional DAW restore acceptance open. A host that appears
to reload successfully may instead be replaying parameter edits or retaining a
live instance; a fresh-instance round trip is required to resolve that
ambiguity after implementation.
[Preset snapshot](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/fullstate),
[document snapshot](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/fullstatefordocument).

All new current API pages were read from the official Apple `.md`
representations in memory because the browser reader returned JavaScript
shells. SDK declarations provide the ramp/lifecycle details. No marketplace,
installation workaround, broad rescan, cache deletion, Gatekeeper change,
host launch, discovery query or registry action occurred. Findings were sent
to the AU owner for the new host-acceptance plan; only this appendix was added.
