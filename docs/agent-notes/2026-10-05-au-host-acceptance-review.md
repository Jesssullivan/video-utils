# Independent AU host acceptance protocol review

Status: corrected documentation protocol accepted; no remaining must-fix.
No host acceptance or activation is claimed.

Authority: root's operator-authorized next-week AU protocol review assignment;
repository contract and R-HOOK-CONVERGENCE-20261004, R-N11/R-N12/R-N13.
Ownership: this dated review note only. Read-only source/document review;
no builds, signing, registry operations, app launch, extension load, audio
device use, Logic operation or host configuration change.

## Established baseline

Packaging was published with `c59d7024a9967b920747e07134c6c166c3ddb38d`.
The prior independent packaging audit accepts only the static bundle built by
the receipt created `2026-10-06T00:06:19.900916+00:00`, SHA-256
`9b0b1f487f1aa45ba3cb405a75fa296fcad6865e5c7783b32fd52b17dd0746b0`.
Registration, factory execution, extension loading, actual window display,
`auval`, Logic, listening and distribution remain unverified.

Current published source constraints, read again for this review:

- `GuitarGainAudioUnit.swift:19,52-72`: generic nonnil `fullState` and
  document-state setters remain unqualified and report local status `-100`.
  Nil is a no-op. Getters may return nil on concurrent ingress publication.
  The stopped checked private restore helper is a separate direct API, not
  proof of DAW project or preset persistence.
- `GuitarGainAudioUnit.swift:77-102`: advertised plugin latency is zero;
  allocation supports matching mono/stereo, noninterleaved Float32, rates
  8000-384000 and maximum block size 1-4096. Device/host round-trip latency is
  a different measurement from the plugin's sample alignment or control ramp.
- Published integration retains a 64-frame control ramp, explicit scheduled
  step/ramp processing and latest-target coalescing. A getter reports the
  target rather than the ramp's instantaneous audio multiplier. No transport
  seek/reset policy or hard realtime bound is established by the static package.

## Review criteria

Check the concrete protocol for artifact and executable hash binding,
authorization before each newly released class of host action, bounded owned
processes and session/device scope, registry/discovery evidence independent
of prior static evidence, actual extension/factory execution independent of
direct-constructor harnesses, format and lifecycle coverage, measured gain
and automation behavior, explicit current state failure expectations, sample
alignment distinct from device latency, and truthful security/signature and
performance limitations.

## Concrete protocol review

Reviewed `docs/spec/AU_HOST_ACCEPTANCE_LANE.md`, SHA-256
`9b6f71c09217cc658775dec4ee88d5bf72be194bd9e41a0a3aac28b588d0f246`.
No native or root Rust/lock changes were present against published `c59d702`
after the review. No specification was edited by this audit lane.

The seven stages preserve distinct proof classes: source/static package,
installation, discovery, registered extension render, parameter/state,
validator and actual Logic behavior. Each retains pass/fail/blocked/not-performed
status. A partial render pass cannot promote the current restore rejection to
saved-session reliability. Native state/bypass changes and a new host harness
require exact ownership release, source regression checks, a fresh artifact
receipt and independent review before activation.

The future action proposal names the candidate, Applications destination,
containing-app launch, filtered registry query and targeted validator. It first
requires actual scoped authorization, absent-destination/collision checks and
post-copy identity/signature verification. The plan explicitly accounts for
automatic registry updates on installation and permits no cache reset,
election change, Gatekeeper/quarantine bypass, unrelated process termination or
credential borrowing. Ad-hoc sandbox-only signatures remain local packaging
evidence. Device and Logic actions require their own explicit scope, disposable
owned project and preservation of existing device configuration.

Registered fixtures must instantiate through standard asynchronous APIs and
render the returned registered AU, rather than construct the concrete Swift
class directly. Startup and fixture attempts are bounded. Main-thread waits and
callback I/O/allocation/model/subprocess work are excluded. Ambiguous observed
process mode cannot pass the specifically out-of-process claim; narrower
registered-render evidence may survive independently. Private direct-instance
restore/status APIs are not assumed available through a remote AU proxy.

State and bypass acceptance remain real obligations. Standard state/document
and actual Logic recall require coherent parameter/private-payload/output
round trips and transactional rejection. Active recall, quiescence, seek,
interrupted-ramp reset and bypass progression need a released source contract;
the current nonnil setter rejection is a limitation, not a passing test.

Timing separates sample alignment, 64-frame control smoothing, render/IPC wall
time and device round trip. The plan retains previous measured outliers and
requires reporting every observed deadline exceedance and host dropout. A
hardware-free offline fixture or zero advertised AU latency cannot establish
scheduled realtime deadlines or monitored hardware latency. The 35-70 hour
week is a conditional allocation, with blockers and partial gain-only evidence
preserved; it does not promise a denoising plugin or acceptance without the
required future actions.

## Findings resolved before acceptance

1. Constant-gain sample comparisons initially omitted preparation semantics.
   Setting a prepared unit from default gain 1 invokes its 64-frame control
   ramp. The corrected protocol sets each target while resources are released,
   allocates, then checks first-frame `input × gain`.
2. The initial scheduling paragraph did not distinguish the step's first
   sample from a ramp's first sample or specify all gain targets. The corrected
   independent oracle starts at gain 1, steps to 0.5 at frame 37, ramps toward
   2 from frame 61 for 256 frames, then interrupts at 173 with a 64-frame ramp
   to 0.25. The interruption begins at gain 1.15625 and reaches 0.25 at frame
   237. A separate immediate-input step uses 0.75 at offset 17. These values
   agree with the unchanged engine's start/advance convention; equivalent
   absolute frames must agree across block partitions.
3. Requesting out-of-process loading alone initially left its acceptance
   consequence implicit. The corrected text marks unavailable/ambiguous
   observed mode unknown and excludes it from the out-of-process pass.

Read-only primary checks also confirmed installed SDK
`AUAudioUnit.h:363-380` warns against blocking the main thread for asynchronous
instantiation; `AudioComponent.h:234-239` says loading options may fall back;
`AUAudioUnit.h:960-978` defines processing impulse delay; and
`AVAudioEngine.h:83-100` separates manual rendering from device rendering and
offline execution from realtime constraints. The installed PlugInKit manual
confirms filtered identifier matching and all-version/duplicate options. These
were file reads, not API calls, registry queries or host validation runs.

The reviewed protocol is ready for root integration as future work. Its host
harness, revised state/bypass implementation, activation and all host results
remain unimplemented or not performed. The previous packaging static-only
acceptance is unchanged.
