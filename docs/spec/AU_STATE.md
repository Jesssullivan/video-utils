# Isolated native parameter-state milestone

Definition of done, recorded before implementation: a dependency-free bounded
state codec and stopped-lifecycle restore experiment must round-trip its typed
versioned payload, reject corrupt, out-of-range, stale and incompatible data
without partial mutation, and initialize the published gain-automation engine
before its first render. Tests must verify first-frame gain, subsequent control
ramping, producer/consumer boundaries and unchanged earlier native sources.
Builds use installed tools, one job and finite command deadlines. This lane owns
only `native/au-spike/state/` and this document.

## Apple contract and claim boundary

Apple's [fullState](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/fullstate)
is a persistable parameter/property snapshot for presets. It excludes transitory
stream formats. The base implementation serializes parameter-tree values.
[fullStateForDocument](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/fullstatefordocument)
can include additional document-specific state and otherwise delegates to
`fullState`. The installed macOS SDK's `AUAudioUnit.h` declarations supplement
the current web documentation. A future AU wrapper must preserve superclass
state and parameter notifications; this experiment implements neither setter
nor an Apple preset dictionary.

The wire format below is a private experimental codec, not `.aupreset`, Apple
ClassInfo, a DAW document, registered component state or Logic automation.
No package, plugin registration, device, application or host configuration is
changed. Existing gain ABI, kernel, Swift and automation sources remain frozen.

## Proposed bounded representation and lifecycle

- Exactly 32 bytes, canonical little-endian encoding: magic `VUST`, schema u16,
  length u16, identity u32, gain ABI u32, parameter address u64, gain Float32 bits
  u32 and reserved u32. Schema 1, experiment identity `0x47554e31`, ABI 1,
  address 0, finite linear gain `[0,16]`, reserved 0. No filename, media path,
  stream format, model identifier, pointer or render-ramp progress is persisted.
- The controller keeps a separate nonpersisted u64 revision. Restore requires
  an expected revision; stale work and revision exhaustion reject before
  mutation. Repeated user recall of an old preset remains allowed when the
  caller supplies the controller's current revision. Revision is concurrency
  metadata, not a prohibition on older musical presets.
- Serialization and validation run on one serialized control owner, outside
  rendering. Typed values and a caller-owned fixed output buffer avoid parsers,
  Foundation object ownership and unbounded allocations. Rejected payloads
  leave controller/output state untouched; invalid caller storage remains a
  caller obligation.
- Restore is allowed only before rendering or after the caller has stopped all
  processing and destroyed the previous engine. Publish the validated gain to
  the existing lock-free mailbox before constructing a new automation engine;
  its first frame uses that restored gain immediately. The gate itself does not
  stop threads, wait for callbacks or prove a host has stopped rendering.
- While active, preset restore rejects. Ordinary active parameter edits use
  the existing single-producer latest-value mailbox and its 64-frame smoothing.
  The control owner serializes every mailbox publication; the renderer has
  exclusive ownership of engine state. No state parsing, locks, retry loops,
  I/O or serialization enters the render path. Timeline automation remains a
  separate event-list path and is not captured by this control snapshot.

## Planned qualification

Test canonical bytes/endian conversion, exact Float32 bit round-trips (including
signed zero), every truncated length and trailing bytes, unknown schema/identity/
ABI/address, reserved fields, NaN/infinity/negative/out-of-range gain, stale
revision, exhaustion and failed-restore rollback. Test restored first-frame
gain in mono/stereo, active-restore rejection, stopped restart and active-edit
smooth transition using the unchanged Rust-backed engine. Count allocations
only during processing, inspect render-side object references, run bounded
ASan/UBSan fixtures, and record immutable source hashes with no AU-host claim.

| Checkpoint | State |
| --- | --- |
| Primary Apple review and durable definition of done | Observed |
| Codec, lifecycle gate and integration harness | Implemented and compiled |
| Bounded native checks | PASS; 2026-10-05T21:58:19.275096+00:00 |
| Independent native review | PASS; no remaining must-fix |
| AU fullState integration, preset packaging, Logic acceptance | Not performed |

## Native receipt and limitations

`python3 native/au-spike/state/check.py` is a development check. It builds the
unchanged Rust static ABI offline with one job, compiles the state codec/session
and unchanged gain automation, inspects four unoptimized processing bodies,
and runs release plus Address/UndefinedBehaviorSanitizer fixtures. The stable
`.cache/au-state/receipt.json` records both behavior passes, no forbidden direct
runtime references, no source-hash changes during compilation and zero counted
C++ `new` calls across 1000 render blocks. The single-producer stress fixture
published 10000 edits concurrently with processing.

Verified behavior includes exact canonical bytes, signed-zero Float32 round
trips, truncated/trailing/null data, incompatible fields, gain nonfinites/ranges,
stale and exhausted revisions, failed-restore rollback, mono/stereo first-frame
restoration, stopped restart, active-restore rejection and 64-frame control
smoothing. Serialization captures the last control target even when timeline
events have changed the running engine; it intentionally does not infer actual
host-visible parameters from this isolated event path.

The restore gate proves the state machine's checked behavior under its caller
contract, not that a host has stopped its callback. Start/stop/destruction require
no processing in flight. Only one control owner may call edits, snapshots,
serialization or lifecycle methods; after start, that owner may edit concurrently
with one processing consumer. No mutex, allocation, parsing or serialization is
added to rendering. The underlying mailbox still coalesces values and retains
the earlier documented 32-bit sequence-wrap limitation. Counter and direct-call
inspection scopes remain bounded; no arbitrary host callbacks or hard realtime
deadline are qualified. This private payload has no checksum/authentication and
does not replace the future AU wrapper's superclass state handling or parameter
notifications.

Independent read-only review confirmed the codec/lifecycle/concurrency contracts,
the stable receipt hashes and no tracked native/automation changes against
published `6f7d196`. Receipt SHA-256:
`8f60f859069ca25b75997e62172e0141c6cdf375c46a1b9c94bc63962f2391f6`.
ASan/UBSan and the producer stress fixture are not a ThreadSanitizer or actual
host-threading proof. Root owns the development entrypoint and publication;
this lane adds no audio-operation MCP tool or plugin-runtime hook.

Authority: operator ten-hour parallel goal, `GRAPH_INTEGRATION_LANE.md` and root
ownership assignment; R-HOOK-CONVERGENCE-20261004/R-N11/R-N12/R-N13. Generated
artifacts belong under ignored `.cache/au-state/`; root owns publication and
tracker receipts. Repository code remains MIT; Apple SDK terms are separate.
