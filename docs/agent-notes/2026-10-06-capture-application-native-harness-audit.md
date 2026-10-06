# Native capture-application harness source admission audit

Owner `/root/release_review`; root explicitly authorized read-only harness
admission review under operator parallel goal and
R-HOOK-CONVERGENCE-20261004/R-N13. Root owns frozen source release and execution.

Definition of done: inspect exact release/source/environment pins, one generated
eight-second stereo/VFR fixture, 600-second/two-thread bounds, native origins and
capture/sample mapping, residue/calibration/export checks, protected original/
parent/latest artifacts and truthful failure recovery. Read source and inert
test definitions only. No harness import/execution, generation, FFmpeg, DSP,
model, dependency or host action is authorized by this audit. Application
post-commit repair must independently pass before native release.

Initial plan SHA:
`f2aa237b4d7c0a34e93e5065e7436639a20311c7a81945de196c39c985ecd683`.
Initial harness intentionally retains old application `31eafcc8…` until the
separately released correction freezes; this is an execution hold, not an
accepted current pin.

## Initial source readback

Closed release binds preregistration, plan, harness, workers, output and existing
FFmpeg/FFprobe binary bytes. Fresh output and stale-setting/source rejection
precede application import. Fixed generation is eight seconds, stereo44.1k,
352800 frames, deterministic integer PCM and one 175-frame VFR MOV. Picture
origin1/audio1.5 and capture[11025,44100) are preregistered. Fixed NR3/NF-40,
adaptivity0/smoothing0, -18LUFS/-1.5dBTP, no EQ/compressor are retained. Existing
bypass baseline, authoring and application create separate unreviewed runs.

Whole-owned alarm and remaining-time runners bound execution; logs/process
groups use the application runner. Protected actual-take files are hash-read
only, never numerically decoded by this harness. Parent/profile/review/reference
artifacts and latest/master pointers are rechecked. Pure source-minus-denoised
residue, exact native headers/counts and calibrated delay1102/remnant0 remain
separate from listening quality. Actual video frames provide rational VFR PTS/
duration checks; existing exporter provides copied-packet payload/timeline and
strict final AAC peak evidence. Raw AAC padding is recorded separately.

## Findings sent before freeze

1. Current application repair uses `committed_candidate`; initial harness
   listened only for legacy `published_candidate`. Owner has corrected recovery
   lookup and its inert regression, retaining candidate selectors and failure
   receipt identity without asserting absence. Its alarm now raises application
   `ApplyError` so the application preserves recovery evidence.
2. Verify generated s16 reference samples against baseline float32 source PCM
   using exact /32768 mapping. Initial harness only compared two decodes of the
   MOV; shared channel/gain/offset errors could satisfy both equality checks.
   This strengthens native transport proof, not musical fidelity.
3. Independently derive first decoded AAC origin from retained PTS/time_base
   and compare with first picture origin against expected0.5s, within existing
   1024/44100+0.002 tolerance. Initial harness delegated the gate entirely to
   exporter metadata while retaining raw rows. Keep AAC padding count distinct.

## Updated source readback, awaiting release identities

The harness now gates generated s16 reference values against baseline native
float32 PCM using exact signed /32768 mapping, then independently compares the
candidate decode against that baseline. The pure-constant test includes signed
limits and alternating channel values. It also derives decoded AAC frame origin
from integer PTS and rational audio time base, independently requiring the
expected half-second picture/audio offset within 1024/44100+0.002 seconds.
Packet priming and decoded padding counts remain separate evidence. The inert
regression rejects a zero audio origin while retaining the padding count.

A further integration finding was sent to the harness owner: corrected
application publication deliberately disarms its matching owned alarm when it
records a committed candidate. The larger harness supplies that matching alarm
and continues qualification after `apply` returns. The owner added
`resume_qualification_alarm`: it rearms the outer absolute deadline immediately
after `apply`, then routes later qualification commands through the existing
owned runner and rearms after each cleanup. Completed application recovery
remains intact; the scoped media helper restores on context exit. The new inert
test simulates two completed-application cleanup contexts and verifies the alarm
is active after both while `LAST_COMMITTED` retains the same recovery object.
No application algorithm or publication semantics were changed for this fix.

The independently reproduced application observation failure is also represented
separately in harness failure evidence: the actual exception's
`possible_candidate` or `LAST_POSSIBLE_CANDIDATE` retains the prepared candidate,
and the harness derives `unknown_after_publish_attempt` when no confirmed commit
exists. Confirmed recovery takes precedence. A new inert test retains the possible run/hash,
requires `unknown_after_publish_attempt`, rejects a confirmed recovery field,
and keeps `candidate_absence_asserted` false. It starts no generation or media
command. The application's matching fields were source-read and independently
exercised in the nine mocked-media audit cases. No nonexistent exception outcome
attribute is required.

Final admission awaits corrected application freeze and freshly bound
preregistration/release identities. Owner reports thirteen
inert harness tests passed; this audit reads their definitions and has executed
none. No native qualification result is claimed.

## Final exact identity admission readback

The implementation owner froze harness
`c0268e80fdfb3ee17791534d078c0707f077c3ab0efac490fe2ee7bcc27142ee`
and test source
`6e2b8248b857806def5573e45a0bb46cd83eccf740d3be18e7d6e268f952d9bb`.
Owner receipt reports 14 inert tests passed in 0.245 seconds. The fourteenth
definition rejects both active and interval-only preexisting timers before any
timer or environment mutation; the source matches that invariant. This lane
executed no harness import or inert test.

Independent metadata-only readback passed: preregistration
`docs/agent-notes/2026-10-06-capture-application-native-qualification-preregistration.json`
SHA `0eca36a73660f797c18d122bbad6d29cfa0b9815c291557d5329089e0c70320c`
binds exact application `00a03ef9…`, authoring `7d282087…`, media `91443154…`,
current harness, historical plan `f2aa237b…` and bypass profile
`6f2d2117a6ba33ff5fa3e2daf6052d4d241186dfb62687c5ce8c55ffa1408865`.
AST-read source PINS/FACTS/CONTROLS equal preregistered values; kept picture
indices are exactly the 175 specified values; bounds remain 600 seconds and
two threads. Both installed FFmpeg/FFprobe byte hashes independently match
their metadata; version8.1.2 remains a runtime capability gate, not an executed
version claim from this audit.

Fresh output `artifacts/experiments/capture-application-native-qualification/native-20261006T0255`
was absent with nonsymlink ancestry at this readback. Freeze receipt SHA
`0065825a63da9e590f691f204f465a995edef660003b870b249786bc23e42d93`
binds root application-freeze receipt SHA
`ccfe05317bbb9217efacd06168502d3b9b83c9a1880b4a2f8ecb236d8f26d228`
and exact owner file hashes. Independent application cases passed on the same
frozen bytes; the 46-case combined log was read and hashed separately.

No remaining source/identity admission blocker exists for root's single
generated-eight-second native qualification. Root alone creates the closed
execution release and runs it. No generated media, DSP, actual-recording
processing, listening acceptance or master adoption has occurred in this lane.
Saved native artifacts require a separate post-execution audit.
