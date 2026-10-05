# Plan: integrate gain parameters, automation and private state into the AU scaffold

This is a plan-first continuation of the operator's ten-hour goal ending
October 6 at 06:49:34 UTC. Baseline is published `45a1313`. The current lane
initially owned only this document. Root has released exactly the implementation
ownership table below; automation/state/Rust/ABI/locks remain frozen. The initial
checkpoint contained no implementation/build. Bounded integration results are
now recorded below. Extension packaging, registration, `auval`, device use and
Logic load remain outside this milestone.

## Observed source and primary contracts

The published Swift `GuitarGainAudioUnit` constructs matching planar mono/stereo
buses and delegates its internal render block to `VUGainKernel`. It exposes no
gain parameter tree or state override. The kernel applies one block-constant
gain and rejects every non-null event list. Its cached native block owns its
state safely; its pull-input argument is explicitly unsafe-unretained.

The isolated automation engine already implements a 64-frame control ramp,
sample-frame steps/ramps, interruption and continuation, one gain address and
bounded event conversion. It accepts interleaved data rather than the existing
planar bus format. `vus::Session` wraps that engine with stopped-only restoration,
single-control-owner revision checks and the canonical 32-byte codec. It has
no Apple parameter callbacks. Its mailbox is single-producer; calling Session
edits directly from arbitrary parameter callbacks would violate that contract.

Apple's current declarations distinguish implementation callbacks from client
observers. The implementor observer stores external changes in DSP state; the
provider supplies its value when the parameter object needs refreshing. Client
observer notifications are throttled, run in an arbitrary thread context and
must not add/remove observers from their callback. Removing observers waits for
in-flight calls. This plan adds no client observer as the DSP control path.

The base `scheduleParameterBlock` is safe from any thread, including realtime
threads, and subclasses should not override it. It delivers absolute-time
render events after translating scheduling-input immediate offsets. Parameter
tree mutation is not realtime-safe. Allocate/deallocate belong before/after
rendering and must call the superclass; these methods do not prove a hostile or
misbehaving caller has stopped callbacks. `fullState` persists parameters/custom
properties, not stream formats; the document variant can delegate to it.

Primary references inspected October 5, 2026:

- [Implementor value observer](https://developer.apple.com/documentation/audiotoolbox/auparameternode/implementorvalueobserver)
  and [implementor value provider](https://developer.apple.com/documentation/audiotoolbox/auparameternode/implementorvalueprovider).
- [Client parameter observer](https://developer.apple.com/documentation/audiotoolbox/auparameternode/token(byaddingparameterobserver:))
  and [parameter value/originator](https://developer.apple.com/documentation/audiotoolbox/auparameter/setvalue(_:originator:)).
- [Parameter scheduling](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/scheduleparameterblock),
  [fullState](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/fullstate)
  and [fullStateForDocument](https://developer.apple.com/documentation/audiotoolbox/auaudiounit/fullstatefordocument).
- Installed macOS SDK `AUParameters.h`, `AUAudioUnitImplementation.h` and
  `AUAudioUnit.h` supply the declaration/comment details above; the web pages
  require JavaScript. No Apple source is copied into the repository.

## Supported parameter and control paths

Create one stable cached tree at initialization: identifier `gain`, name `Gain`,
address 0, linear-gain units, readable/writable/rampable, minimum 0, maximum 16,
default 1. Use Float32 linear values throughout; no decibel conversion, clipping,
tone or restoration behavior is implied. Do not reconstruct the tree during
rendering. The native callbacks installed on this one-parameter tree do not need
to inspect or retain their AUParameter argument.

The observer and provider blocks originate in Objective-C++ and capture native
shared ownership while their getters execute outside rendering. Their invocation
bodies use native atomics only; AUParameter arguments are unsafe-unretained and
unused. Swift wires these blocks to the tree but supplies no Swift closure in
the processing/callback path. There is no self/parameter/native-state retain
cycle. Cached blocks can survive wrapper destruction but cannot render an
unprepared unit. Direct object-code inspection must confirm the intended ARC
boundary, rather than relying on source appearance.

External callbacks feed a new fixed native atomic ingress, not `Session::edit`.
Use a lock-free UInt64 word containing Float32 bits and a UInt32 publication
ticket plus a control/feedback source tag. Ticket zero denotes the initial value;
a separate lock-free UInt32 `fetch_add` starts at one and supplies tickets; each changed target
publishes with one atomic exchange. Same-bit targets are idempotent and do not
restart or interrupt an ongoing ramp; timeline step events remain explicit.
Concurrent producer ordering is the exchange
order, not ticket magnitude. The consumer compares ticket equality, never signed
ordering. There are no allocation, lock or application-level atomic retry loops. Pending
edits coalesce; this is not a lossless automation queue. After 2^31 ticket reservations,
including failed conditional publications, the tagged ticket wraps, which can
create an ABA observation and remains an explicit limitation.
Reject nonfinite/out-of-range direct values without publishing them. Apple's
own parameter clamping behavior must be measured separately by the harness.

While prepared, the renderer owns Session metadata and the engine. At each
nonempty block it samples ingress once, publishes a changed target through the
Session's single-producer edit API, then processes the fixed event batch. It does
not encode, serialize, query Foundation or call Swift. While stopped, the
serialized lifecycle owner owns Session restore/start/stop. Ownership transfers
only after all rendering has stopped; no control method reads active Session
scalar fields from another thread. The provider reads atomic ingress instead.

The provider/persistent parameter value represents the latest target, including
the last scheduled target delivered in a successful block, not a ramp's
intermediate multiplier. After successful processing, the renderer may publish
the last event target with one conditional atomic exchange against the ingress
word sampled for that block, with a fresh feedback-tagged ticket. A concurrent new control
publication wins: one strong compare/exchange call is used, with no application
retry. A feedback-tagged value must not be republished to the Session mailbox next block or
cancel a continuing automation ramp. This distinction needs explicit tests.
Lock-free atomic read/modify/write does not imply wait-free execution: the
compiler/CPU may use implementation-level exclusive-load retries. Inspect
generated atomic instructions and retain that qualification; neither bounded
source-level attempts nor lock-free status proves a hard latency bound.

## Native planar adapter and lifecycle

Keep current buses, matching formats/rates, mono/stereo and 4096-frame limits.
The native state owns fixed planar input/output storage and interleaved working
storage alongside the Session's prepared scratch. Keep pull-input planes
separate from committed output planes, since callers may reuse adopted output
pointers on a later failed render. The three additional stereo arrays require
98304 bytes; combined with engine gain/scratch arrays the fixed array footprint
is 147456 bytes. No buffer growth occurs while rendering.

Validate output metadata and the event list before pulling input. Convert only
delivered absolute event times with the published Apple adapter. For nonempty
events, require valid finite integral sample time within the signed-64 range;
check Float64 boundaries before conversion to avoid undefined integer casts.
Retain the 32-event, 192000-ramp-frame, address/reserved/order constraints and
read-only list ownership. Invalid events reject without silently shifting them.

Pull into native planes, validate returned channels/data/byte bounds, interleave,
process and deinterleave to prepared output planes. Publish caller output only
after processing succeeds. Host null output pointers receive the native planes,
valid until the next call or resource release. Foreign storage validity and
exclusive access remain caller obligations; metadata checks cannot establish
that an arbitrary pointer names a real allocation.

Failed pulls or detected metadata/event/sample/overflow errors must leave caller
output and DSP ramp progression unchanged. A valid already-published user target
remains pending even if that audio block fails; do not roll back the user's
parameter change or claim it was applied to audio. Track ingress publication and
successful DSP consumption as different states. Empty blocks do not advance
ramps or consume pending edits. Unsupported bus/kind/address and uninitialized
rendering return native errors. No error path logs or throws across rendering.

Preparation drains the current validated target while stopped, then constructs
the Session engine so its first frame uses that target. Release first makes
cached blocks unprepared, then stops the Session under caller quiescence.
Superclass allocation/deallocation and failure rollback remain intact. The
existing unsafe-unretained pull-input qualifier remains explicit in both native
helper and block declarations. No implicit realtime reset/seek policy is added.

## Canonical private state and AU dictionary mapping

Reuse `vus::encode/decode` unchanged: exactly 32 bytes, schema 1, experiment
identity `0x47554e31`, gain ABI 1, address 0, finite linear gain `[0,16]`, reserved
zero, canonical little-endian Float32 bits. The native codec remains private;
it is not `.aupreset`, ClassInfo binary compatibility or a portable DAW session.

Add a namespaced Data entry such as `org.video-utils.gain.state.v1` to a copy
of `super.fullState`, retaining superclass metadata/parameter representation.
The document getter uses the same parameter state because this unit has no
additional document-only properties. Do not serialize formats, pointers,
mailbox tickets, Session revisions or partial ramp progress. Obtain the target
from a coherent atomic word on the non-render caller; render code never parses
the dictionary or Data. The getter may operate while prepared. Sample a token
before the superclass getter and again after preparing the private payload;
return nil if publication changed, without retries. Fresh feedback tickets
detect gain changes and return-to-original changes within this window. Test
concurrent callback/feedback getters; every available result must agree.

Restoration requires stopped rendering and one serialized lifecycle owner with
external parameter writers quiesced for the transaction. This source milestone
does not promise concurrent host preset recall while audio is active. Nil input
is a documented no-op. A nonnil input requires exactly one well-typed 32-byte
private payload, compatible unit identity/metadata and a bounded superclass
representation. Reject invalid, conflicting or incomplete input before changing
native state or calling the superclass setter. A checked native restore helper
accepts the expected current Session revision/ingress token for stale-work
rejection; ordinary preset recall takes a fresh token, so an older musical
preset is not rejected merely for being older. Rejected setters preserve prior
state and expose a bounded local status for harness verification. The native
helper copies exactly 32 bytes to owned fixed storage before validating/committing,
so validation and Session restoration consume one stable payload.

Before enabling the setter, the direct-instance harness must record and verify
the actual superclass-generated dictionary shape and parameter round trip.
Do not invent an undocumented Apple parameter encoding. Restrict accepted input
to this unit's generated schema, cap keys/aggregate binary size, and verify that
its superclass gain agrees with the private canonical gain. If that comparison
cannot be established from the observed base representation, keep the checked
private restore helper functional and report `fullState` setter qualification
as unresolved; update this plan before making a broader claim.

For a supported canonical input, forward the validated superclass portion under
stopped/quiesced ownership, restore the canonical target and synchronize the
parameter object without issuing a duplicate ingress edit. Verify superclass
parameter notifications/`allParameterValues` rather than manufacturing KVO or
re-entering the provider through `parameter.value`. Parameter callbacks invoked
by superclass restore still use the bounded native ingress. Restore must finish
with superclass parameter state and the private payload agreeing before the
next allocation. `fullStateForDocument` must follow the same validated path once,
without recursive delegation or double restore. Any failure to demonstrate
these properties keeps AU state integration acceptance explicitly incomplete.

## Proposed exact implementation ownership for root release

| Files | Purpose |
| --- | --- |
| `native/au-spike/apple/GainKernel.h` and `GainKernel.mm` | Native parameter blocks, stopped checked state bridge, Session lifecycle and planar/event integration |
| `native/au-spike/apple/GuitarGainAudioUnit.swift` | Stable gain tree, callback wiring, bounded superclass/private state mapping |
| New `native/au-spike/integration/ControlIngress.hpp` and `.cpp` | Dependency-free bounded multiple-producer ingress and ticket/feedback semantics |
| New `native/au-spike/integration/parameter_state_harness.mm` | Independent native callback, planar/event, control race and state/lifetime fixtures |
| New `native/au-spike/integration/state_harness.swift` | Direct AU tree, superclass dictionary, notifications, scheduling and stopped restore fixtures |
| `native/au-spike/tests/kernel_harness.mm` and `tests/main.swift` | Preserve existing kernel/lifecycle regression coverage under smoothed gain behavior |
| `native/au-spike/check.py` | Link unchanged automation/state sources, audit new callback bodies, include `.cpp/.hpp` source hashes and run bounded integration fixtures |
| This integration plan | Record qualified results, unresolved boundaries and independent review |

No change is proposed to Rust DSP/ABI, Cargo locks, automation source, state
codec/Session source, just recipes or unrelated documentation. Root owns the
just entrypoint and publication. Existing standalone automation/state checks
continue to qualify their unchanged lanes independently.

## Definition of done and independent checks

1. Native source compiles using installed Apple/Rust tools, offline locked Cargo,
   one build job and finite deadlines; generated files remain in ignored cache.
2. Tree tests prove exactly one gain parameter, flags/address/range/default,
   persistence of the tree and provider consistency without recursion. Test
   direct invalid native controls separately from Apple's clamping behavior.
3. Native planar fixtures prove mono/stereo, first-frame restored gain, 64-frame
   control smoothing, exact event frames, cross-block/interrupted ramps and
   null-owned output lifetime. Swift fixtures exercise the actual base render
   and cached schedule blocks on a direct object, not a registered component.
4. Concurrency fixtures exercise multiple callback producers, one renderer,
   exchange-order semantics, coalescing, feedback races and feedback-tagged
   ramp continuation. Lifecycle tests use actual quiescence, and test cached
   blocks after release/destruction. Do not call a concurrent start/stop test
   safe merely because the caller has violated the stated lifecycle contract.
5. State tests prove canonical superclass/private round trips, nil/type/length/
   schema/identity/gain errors, disagreement rejection, stale checked tokens,
   active-restore rejection, stopped restart and prior-state retention. Preserve
   unknown/unqualified superclass behavior in the receipt rather than claiming
   generic AU preset compatibility.
6. Inspect complete compiled render/helper/implementor bodies for ARC/ObjC
   ownership, allocation, locks, I/O and retry loops. Counters qualify 1000
   processing calls; release and bounded ASan/UBSan fixtures supplement source
   review. Producer stress is not TSAN; timing is not a hard realtime guarantee.
7. An independent read-only native review checks source ownership, race and
   lifecycle reasoning, state transactions and all receipt/source hashes. Root
   reviews the concrete result and publishes; no host or plugin changes occur.

Report separate states: source implemented, native compiled, direct AU object
tested, state setter qualified/unresolved, packaged extension, registered
component, `auval`, Logic load and listening. The last five remain not performed
throughout this source-only integration milestone.

Authority: operator goal and root plan-first assignment;
R-HOOK-CONVERGENCE-20261004/R-N11/R-N12/R-N13. No approval gate is inferred from
advisory hooks; the existing-code freeze is an explicit root ownership boundary.

## Qualified source/native checkpoint

Stable receipt: `.cache/au-spike/receipt.json`, created
`2026-10-05T23:07:34.933646+00:00`, status
`native_checks_passed_not_au_host_qualified`, SHA-256
`bc2cc83685df658105dfa5a28ee945c044971ed5dee8dc3972fceeb33bf05955`.
All compiled-source hashes match. Independent read-only review accepted the
final source and four complete render/helper/implementor bodies, with no
forbidden direct runtime references. Supporting Session/engine/event/ingress
objects also passed bounded named-function inspection. Frozen automation,
state, Rust, ABI and Cargo files remain unchanged against `45a1313`.

| Evidence | Observed result |
| --- | --- |
| Original Rust/C/kernel/Swift lifecycle checks | PASS |
| Native parameter/state release harness | PASS; 20000 producer callbacks, 1000 render calls, zero counted C++ `new` |
| Native Address/UndefinedBehaviorSanitizer harness | PASS; separate instrumentation scope, unchanged Rust ABI separately tested |
| Direct Swift AU object | PASS; one gain tree, base scheduling frame tests, continued ramps, checked stopped restore and restart |
| Concurrent guarded state getters | 965 available, 35 nil out of 1000; finite bounded private payloads and observed guard behavior |
| Superclass dictionary | `data` Data(21), numeric manufacturer/subtype/type/version; wrapper adds private Data(32) |
| Generic `fullState` setter | UNQUALIFIED; nonnil input rejected with local status -100, nil is a no-op |
| Packaging, component registration, `auval`, Logic and listening | Not performed |

The private restore helper is implemented with expected revision/ingress token,
stable 32-byte copy, all native rejection conditions before publication, and
stopped lifecycle ownership. It synchronizes the sole parameter object after
successful native restoration; idempotent native targets avoid an extra ingress
publication. The direct harness confirms first-frame mono/stereo behavior,
stale/incompatible/active rejection and restart. Native fixtures cover invalid
sample-time flags/fractional/nonfinite/signed bounds, pending control after
failed audio, same-target ramp continuation and later-control feedback races.

The initial integration reused output planes for pull-input scratch. Independent
review found that an adopted output pointer reused on a later failing block
could be mutated before validation. The corrected source uses separate input
planes. Regression fixtures retain both adopted channels across failed pull and
nonfinite input, then prove that the pending 64-frame ramp resumes from the
unchanged DSP state. Native fixed-array storage is 147456 bytes.

The 21-byte superclass encoding is opaque. Getter stress proves bounded private
payloads, native token guarding and observed nil-on-conflict behavior; it does
not establish agreement with every encoded superclass field. Accordingly the
setter stays explicitly unqualified and does not forward arbitrary dictionaries
to the superclass. `restoreGainState`/native checked restore is the supported
source experiment. The local ASFW control/MIDI pattern similarly adds private
state to superclass dictionaries without qualifying gain-parameter encoding;
it supplies no audio-render or transaction proof for this integration.

Apple's direct parameter value after an attempted value 17 was 1 in this fixture.
That measurement is not a claim that every Apple implementation clamps to 16.
The native ingress consistently rejects values outside `[0,16]`. Producer
stress and ASan/UBSan are not TSAN, wait-free or hard realtime proof. No latency
guarantee or host-safe concurrent lifecycle claim is added. Root owns the just
development entrypoint, final review and publication.
