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
