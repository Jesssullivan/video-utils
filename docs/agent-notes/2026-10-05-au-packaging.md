# AUv3 packaging prototype receipt

Actor `/root/au_architecture`; owned new `native/au-spike/packaging/**`, `docs/spec/AU_PACKAGING_LANE.md` and this receipt. Authority: operator-approved full-force repository-only packaging lane; R-HOOK-CONVERGENCE-20261004, R-N12/R-N13. Published native baseline `eb378bd33e6c1ab408245e58f93430a495efbf6b` stayed unchanged. Root owns recipe integration and publication.

## Result

**Compiled, ad-hoc signed and statically inspected; not activated.** The manual target graph produces `.cache/au-packaging/VideoUtilsGainPrototype.app` with one embedded `Contents/PlugIns/VideoUtilsGain.appex`. No containing-app window was displayed; the factory, extension and AU were not loaded by this packaging check. No app launch, registration command, plugin installation, `auval`, audio-device or Logic action was invoked. The receipt describes the lane's own actions, not an unsampled global registry state.

The final receipt `.cache/au-packaging/receipt.json` was created `2026-10-06T00:06:19.900916+00:00`; SHA256 `9b0b1f487f1aa45ba3cb405a75fa296fcad6865e5c7783b32fd52b17dd0746b0`; status `bundle_compiled_signed_inspected_not_activated`. Twenty-seven source hashes stayed stable across the build: twenty-one frozen baseline files including the root license, plus six packaging files. Compilers read isolated copies under the ignored lane cache, not mutable source paths. No package/toolchain downloads occurred.

| Evidence | Result |
| --- | --- |
| Target identities | Container `org.video-utils.gain.prototype`; extension `org.video-utils.gain.prototype.audio-unit`; `aufx`/`vuGn`/`Jess`, version65536; prototype IDs, not registered vendor allocation/collision proof |
| Non-UI metadata | `com.apple.AudioUnit`, explicit Objective-C principal `VideoUtilsGainFactory`, one AudioComponents record, no storyboard; factory identity guards compiled |
| Native toolchain | Rust1.95.0; Apple Swift6.4; selected macOS SDK27.0; macOS26.0 deployment target; current machine macOS26.7.1, arm64 |
| Mach-O | Each binary is one thin ARM64 `EXECUTE`, exactly one LC_MAIN and LC_BUILD_VERSION; validated platformmacOS/minOS26/sdk27 |
| Signing | Explicit extension-before-container ad-hoc signatures; `codesign --verify --strict --deep` PASS; each signed entitlement dictionary contains only app-sandbox=true; no Developer ID/notarization/distribution claim |
| Linkage | Every listed dynamic dependency is under `/System/Library/` or `/usr/lib/`; Rust static gain ABI included; no embedded/private dylib |
| Symbols | Defined factory, GuitarGainAudioUnit and vu_gain_process symbols; Apple's `_NSExtensionMain` reference; linkage only, no factory/entry execution |
| Inventory | Exact eight files: app and extension each contain Info.plist, executable, CodeResources and the hash-bound root MIT LICENSE |
| Contract tests | Five PASS: identity/layout drift, path escape, hidden metadata/UI mismatch, external/rpath dependency rejection, extra slices/wrong CPU/platform/minOS/SDK/missing entry |
| Build resources | One Cargo/Swift job; finite120second subprocess limits; twenty-eight compiler/signature/inspection commands; owned compiler groups only may be stopped on timeout after live identity check; no timeout occurred |

Final extension executable SHA256 `9606cda0e3d961e382ff797c4fb223f7d9cc44a735399da3a09c9430bf469b67`; container executable SHA256 `84cc59acb22cafb8a7802147586cb3d3375d748804df6d0942d3cb1c3062732f`; isolated Rust static library SHA256 `08e39066f97c9a9cd6d41237d0b310a445a5eb8841eba5ccc219736a35503b50`.

## Claim limits and handoff

This is a direct compiler-based bundle prototype, not an Xcode project or a distributed application. Direct commands avoid Xcode target steps that can register apps with Launch Services. Native gain/automation/private-state qualification comes from the previously published direct-instance and native receipts; packaging neither expands that DSP nor upgrades those proofs to extension runtime. Existing `fullStateSetterQualified=false` and non-nil generic setters' `-100` rejection are hash-bound and preserved. Checked private stopped-state restore remains the only qualified restore path.

Primary basis and design: `docs/spec/AU_PACKAGING_LANE.md`. Independent source reference note: `docs/agent-notes/2026-10-05-au-extension-packaging-sources.md`. Independent artifact audit: `docs/agent-notes/2026-10-05-au-packaging-audit.md`, owned by the audit agent. Audit feedback strengthened the thin-image/minOS/SDK validator before final freeze. The auditor accepted the final receipt after a fresh read-only recheck of all27 source/snapshot hashes, all21 baseline hashes, licenses, metadata, symbols, binary hashes and strict/deep signatures, with no remaining must-fix. Acceptance is bounded to static packaging.

Reproduce design only with `python3 native/au-spike/packaging/build.py --dry-run`, contract checks with `python3 native/au-spike/packaging/tests.py`, and explicit bounded compilation/signing with `python3 native/au-spike/packaging/build.py --build`. Root may add a developer-only just recipe; this is not an audio-processing MCP operation. Packaging sources are frozen for root review. Future host activation requires root to present the concrete bundle and proposed action for user approval; no such activation is part of this lane.
