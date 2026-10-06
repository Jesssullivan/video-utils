# Independent AU packaging audit

Status: concrete source and generated bundle accepted for bounded static
inspection; no must-fix found. Activation and host acceptance remain unverified.

Authority: root's packaging audit assignment under the operator's active goal;
R-HOOK-CONVERGENCE-20261004, R-N11/R-N12/R-N13. The audit lane owns this receipt
only. It performs read-only inspection of packaging sources and generated
artifacts, with no duplicate builds, activation, registration, signing, device
use, plugin repair or host configuration changes.

## Published integration baseline

- Published baseline and verified HEAD:
  `eb378bd33e6c1ab408245e58f93430a495efbf6b`.

## Review boundary

Inspect the concrete containing-app/extension layout, Info.plist
component identifiers and factory wiring, entitlements/signature evidence,
binary load commands, bundle resource references and any window resources.
Keep source/bundle inspection separate from successful extension discovery,
registration, `auval`, Logic loading and listening.

The published Swift scaffold still sets `fullStateSetterQualified = false`.
Nonnil `fullState` restoration reports local status `-100`; nil is a no-op.
Packaging must preserve that unresolved superclass-state boundary.

## Plan review

Reviewed `docs/spec/AU_PACKAGING_LANE.md`. No design contradiction found in its
non-UI `com.apple.AudioUnit` extension, `NSObject` factory, nested `XPC!` bundle,
`aufx`/`vuGn`/`Jess` component identity, isolated source copies or direct compiler
graph. Installed SDK `AUAudioUnitImplementation.h:448-476` confirms the non-UI
principal/factory contract and the inherited extension-request protocol.

The plan allows ad-hoc signing of owned cache artifacts, followed by static
inspection; it explicitly forbids launching, dynamic bundle loading, registry
tools, plugin-folder writes and host operations. Ad-hoc signature verification
and `_NSExtensionMain` linkage establish packaging inspection only. Window
source/resource presence must remain separate from a displayed application
window; extension creation/runtime remains untested.

## Source review

Reviewed `native/au-spike/packaging/{build.py,tests.py,targets.json,
AudioUnitFactory.swift,ContainerApp.swift,README.md}`. The factory checks
`aufx`/`vuGn`/`Jess` before constructing the unchanged AU. Its Objective-C class
name matches `NSExtensionPrincipalClass`. Metadata contains exactly one
`NSExtensionAttributes.AudioComponents` entry; the extension point is
`com.apple.AudioUnit`, with no editor storyboard or AUv2 C factory function.

The build validates the exact reviewed target identities and layout, copies
hash-bound sources to its owned ignored cache, uses offline locked single-job
Cargo and bounded compiler subprocesses, and signs the extension before the
container. Timeout signalling is restricted to its own live child/process
group. The command graph invokes compilers, signature tools and static
inspection; it contains no app launch, dynamic bundle load, registry command,
plugin-folder write, audio device use or host action. Five contract tests were
reported passing by the owner; this audit inspected their coverage and did not
rerun tests or builds.

`ContainerApp.swift` constructs its informational AppKit window in code. The
eight-file bundle has no nib, storyboard or separate window resource. Both
targets include an unchanged copy of the hash-bound root MIT license in
`Contents/Resources/LICENSE`. This is
source/linkage evidence only; no window was displayed by either lane.

## Independent generated-artifact evidence

Inspected `.cache/au-packaging/receipt.json`, created
`2026-10-06T00:06:19.900916+00:00`, with status
`bundle_compiled_signed_inspected_not_activated`. Its SHA-256 is
`9b0b1f487f1aa45ba3cb405a75fa296fcad6865e5c7783b32fd52b17dd0746b0`.

- All 27 source hashes match both the working files and copied snapshot. All
  21 frozen source hashes match published `eb378bd`; this includes root Rust,
  native Rust/ABI, Swift AU, kernel, automation, state and control ingress.
- Both executable hashes match the receipt. The containing app has exactly
  the recorded eight files, including the nested extension, both signature
  resource seals and both MIT license copies; no symlinks occur in the bundle.
  Both embedded licenses match the root license byte for byte.
- Independently parsed both plists: `APPL` container and nested `XPC!`
  extension, correct executable/identifier pairs, principal
  `VideoUtilsGainFactory`, and one reviewed component version `65536`.
- Independent `codesign --verify --strict --deep` returned 0. Both signatures
  report ad-hoc identity, the exact bundle identifier, no team identifier and
  only `com.apple.security.app-sandbox = true`. This does not qualify
  notarization, distribution or sandbox behavior at runtime.
- Independent `otool -hv/-l` shows both binaries are thin ARM64 `EXECUTE` with
  `LC_MAIN`, macOS platform 1, minimum OS 26.0 and SDK 27.0. Their `otool -L`
  dependencies exactly match the receipt and use only `/System/Library/` or
  `/usr/lib/`; there is no `LC_RPATH` or external dynamic library in these
  binaries.
- Independent `nm -g` confirms defined Objective-C factory and AU classes and
  `_vu_gain_process`, with an undefined import of Apple's `_NSExtensionMain`.
  The extension `LC_MAIN` entry offset is 719328; the container's is 9048.
  Static linkage is not execution of that entrypoint or factory.

| Executable | SHA-256 |
| --- | --- |
| Extension | `9606cda0e3d961e382ff797c4fb223f7d9cc44a735399da3a09c9430bf469b67` |
| Container | `84cc59acb22cafb8a7802147586cb3d3375d748804df6d0942d3cb1c3062732f` |

## Acceptance limits

The current artifacts meet the reviewed architecture, deployment and metadata
contract. The final `validate_macho` guard in `build.py:97` parses one exact
ARM64 `MH_MAGIC_64`/`EXECUTE` header, one macOS `LC_BUILD_VERSION` with matching
26.0 minimum OS and 27.0 SDK, and one `LC_MAIN`. Its added negative fixture
covers multiple architecture headers, a wrong CPU, wrong minimum OS, wrong
SDK, wrong platform and a missing main entry. This audit inspected the parser
and fixture and independently confirmed the current artifact values above.

The direct compiler graph and imported `_NSExtensionMain` remain prototype
feasibility evidence. The factory was not executed, the extension was not
loaded, the app was not launched, and registration, `auval`, Logic, window
appearance and listening remain unverified. The receipt describes this lane's
owned actions, not a sampled global registry state. Published generic
`fullState` restoration remains unqualified and rejecting; packaging does not
change that boundary or extend prior direct-instance render evidence to an AU
host.

No builds, tests, signing, activation, registration, media processing or host
configuration changes were performed by the independent audit lane. It wrote
only this assigned durable receipt.
