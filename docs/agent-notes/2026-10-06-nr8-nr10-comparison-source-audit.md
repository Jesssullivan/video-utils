# NR8/NR10 comparison driver: independent source audit

Authority: root's delegated read-only comparison-driver source audit; operator
active parallel goal, R-HOOK-CONVERGENCE-20261004 / R-N11 / R-N13. Owner
`repo_patterns` owns this note and a separate independent audit fixture if
needed. Comparison source/tests belong to `audio_research`; application/media
workers, candidate rendering, actual measurement release and publication remain
separate owner/root lanes. No actual audio, FFmpeg metering or candidate
measurement is authorized at this source checkpoint.

At orientation the single shared worktree was `main`, HEAD6d021e5; active dirty
adapter/profile/phrase/source-audit writers were preserved. Inspected candidate
driverSHA256
`af5f6c789f131fc18a7ac3d347007fdfcb9dec4a2aa84a1d0f810029635ca269`;
frozen methodSHA256
`9c06f5094966f4b24d832e4b2034810fe9e77300e21ae364c4b9bb41f58d2d0a`.
The owner reports15inert/numeric fixture passes after correcting macOS canonical
temporary paths; owner test SHA1d68460e. These are source fixtures, not the
still-running actual candidate render or an actual comparison receipt.

## Initial findings routed to the source owner

**Deadline coverage:** the af5f6 driver installs its hard55-second SIGALRM only
after release/dependency/protected/candidate hash reads, helper imports and all
native-header inspections. Those earlier phases have cooperative checks but
no hard timer. A bounded inert probe replacing the first provenance read
observed timer0.0seconds, then stopped before any input/audio access. A blocked
preflight/import/header phase can therefore escape the declared processing
deadline. Requested the owned timer cover preflight, refusal to displace an
existing external timer, and unconditional saved-handler restoration even if
the owned runner was never imported. An accelerated inert stalled-preflight
test must prove the corrected path, without audio/FFmpeg calls.

**Partial completed coverage:** candidate descriptions are accumulated locally
and appended to `result.candidates` only after all four role descriptions finish.
A role-loop timeout can therefore lose already completed descriptive metrics.
Requested early candidate creation and incremental recording of completed
roles/panels, with incomplete status/delivery false on interruption. Missing
meter measurements remain missing/null, not borrowed or passed.

Both findings were sent to `audio_research` and root. No shared source edits,
measurement or render rerun occurred in this audit. Initial status is pending
source-owner correction and new exact freeze.

## Source contracts already observed

Closed exact two-candidate nr8/nr10 selectors; root-release driver/method/FFmpeg
hash pins; manifest/application/export/source bindings; original protected
source and shared decoded PCM;7–24distinct protected hashes; both candidates
native44.1kHz mono6,657,385frames; calibrated delay with zero remaining bulk
shift; fixed native origin and explicit physical-sync unknown; native packet/
VFR/payload assertions and bounded AAC padding checks. Actual selector hashes
remain for root's later release; these guards do not constitute artifact proof.

Profile controls match target−18LUFS/−1.75dBTP, fixed300Hz−1.5dB/Q0.8 and
2200Hz+1dB/Q0.8, compressor−18dB/2:1/15ms/100ms/knee3, capture4.10–4.95seconds,
NF−40/adaptivity0/gain-smooth0 and uncertain capture contamination. Only NR8
versus NR10 differs; names/descriptions are presentation metadata. A broad
profile equality check retains fixed hidden wet/mix defaults through the pinned
media producer rather than pretending to measure them independently.

Shared source WAV numeric load occurs once; the original MOV is hashed for
provenance and never decoded by this driver. Four existing stage WAVs are read
per condition; pure source−denoise−residue arithmetic is checked separately.
Only existing mastered WAV and candidate exported AAC enter the qualified00a
owned runner's loudness meter. It uses FFmpeg loudnorm input LUFS/true-peak/LRA
and writes a null sink, never a replacement normalized file. All FFmpeg/
numeric thread settings are capped at two. The old helper's unbounded loudness
function is not called.

Whole/local Welch, source-weighted coherence, fixed quiet/active/tail intervals,
predeclared historical NR8 event anchors and native sample rounding retain the
frozen method. Quiet candidates may contain music; coherence cannot prove low
amplitude preservation; energy changes are mixture changes; historical anchors
are not validated guitar attacks or detector recall. Source/master/AAC stages
remain distinct. Delivery eligibility is separate from preference/listening:
decoded AAC−18±0.3LUFS/≤−1.75dBTP plus structural checks, while music-only/fan-only
gains stay null and listening/master adoption false.

Receipt: `repo_patterns | new independent source-audit note/inert preflight probe
only | verify closed NR8/NR10 measurement scope before actual release |
R-N12/R-N13, R-HOOK-CONVERGENCE-20261004 | source candidateaf5f6, method9c06,
actual candidate rendering underway | two source findings routed, actual
measurement withheld; no source/audio/DSP/adoption changes by this lane`.
## Independent closure on corrected freeze

The source owner corrected both findings and froze driver SHA256
`7f46a7010f42558bf8d39f8a94fc9b0a6f513a12242e61d6be553267d6e9b26e`.
Owner fixture SHA256 is
`cd819f20f73a79ebae94f32c1275bb9635622de3bbae46b1ac9aabcb445fe47e`.
Method/helper/application pins above remain unchanged. Readback confirms the
owned 55-second timer starts before the first provenance read, refuses an
existing external alarm, and restores the saved handler even if imports fail.
The imported owned runner receives the matching alarm handler immediately.
Candidate rows are created before role work; completed descriptions, local
panels and envelopes persist incrementally with explicit incomplete coverage.

Independent new fixture `tests/test_nr8_nr10_comparison_audit.py` checks an
active caller-owned interval timer remains active with its original interval
and handler, no provenance/import access, and false delivery eligibility. A
second oracle observes a running one-shot timer at the first hash boundary,
then raises an inert failure before reading any bytes and confirms restoration
of a custom caller handler and an empty timer. These exercise signal ownership
rather than duplicating audio metric implementation.

Re-ran owner fixtures and both independent oracles on the exact corrected bytes:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_nr8_nr10_comparison*.py' -v
```

Result: **19 PASS in 16.541 seconds**, exit 0, including all three generated
NumPy/SciPy numeric oracles. The first independent run had 18 passes and one
assertion failure because this audit fixture expected the word `timer` rather
than the source's actual `external alarm` refusal text; only the owned assertion
was corrected, with no driver/test-owner changes. Owner separately reports
standard-library execution: 14 passes, three explicit optional-dependency skips.

No actual take samples, candidate WAVs or AAC were loaded for these tests; no
FFmpeg meter or comparison job ran. The single subprocess fixture is the
existing owner oracle's inert Python print command under its owned cleanup
runner. Numeric panels use generated arrays only. Tests do read pinned helper
source bytes and owned temporary metadata placeholders. The source contract
reserves 55 seconds for processing and five seconds for cleanup/reporting;
actual elapsed, complete protected-hash readback, source identity, every
candidate binding and delivery measurements still require the separately
hash-bound root measurement release and its saved receipt. Passing source
fixtures cannot supply that runtime evidence or listening preference.

Final source audit disposition: both material findings closed on 7f46a701;
no remaining source blocker found for root's exact measurement-release review.
Do not adopt a master or infer fan-only/music-only performance from this audit.

Receipt: `repo_patterns | corrected frozen driver readback, owned independent
signal fixture and this note | close early-deadline/partial-coverage findings |
root delegated source audit; R-N11/R-N12/R-N13 | source af5f6 with two findings |
source 7f46a701, 19 fixture passes; actual measurement not executed and master
adoption/listening unverified`.

Subsequent owner handoff: root reports NR8 rendered with qualified application
00a, while NR10 encountered an application cleanup failure after FFmpeg exit 0
and was not published. Protected hashes reportedly remain unchanged. Root will
qualify a separate resource-only application revision before an explicit NR10
retry. Consequently this closure is **historical source evidence for 7f46**;
it does not qualify a future mixed-producer comparison. A successor closed
root-approved producer map and exact owned-runner pin require their own source
review after root freezes the new qualified application SHA. No comparison
measurement is released by this handoff, and this audit has not independently
verified the reported render/failure artifacts.

## Successor producer-map review

Authority: root explicitly resumed the same independent source lane for a
prompt bounded successor review before issuing its own measurement release.
Audio owner source is frozen at
`2322d9e1d2f2309802ba667a80f004261615e16b358d5432123d182dfef72ee2`;
owner tests at
`3cc0c862c22e9890ae03794ebe6c5e38a9baa5db89a74579f170909a68d3d241`.
Both historical source-freeze snapshots read back exactly as 7f46a701/cd819f20.

Reviewed the entire successor delta against that frozen historical driver.
The release now requires the exact two-key producer map:

- nr8: `00a03ef9fad8543be4335cb5cbcd3c9d9580a6b40b8faeb826811b105fd5daa6`
- nr10: `790ac58f1924db2607087c6ab1cdae5d813ba24eda610af1f396d77e93d06584`

Candidate application receipts must match their assigned role. Current owned
meter runner790, archived historical00a and generated resource-qualification
JSON `3ad6a3c119c4e3196604f8818630ec74960028cb1df33e3f3e7c0e3abcb09603`
are additional before/after hash bindings. Shared author7d282/media914,
method9c06, source/PCM identities, profile controls, timer and incremental
coverage logic remain unchanged. Read the 790-versus00a application source
delta: it changes process inspection timeout/retry/reserve/cleanup receipts;
no media filter, profile setting or DSP call changes appear in that delta.
Actual generated qualification artifacts belong to root's independent runtime
lane; reading this summary is not a repeat qualification measurement.

Results explicitly disclose different resource runners, per-candidate producer
hashes and unchanged shared DSP producers. Operator-reported guitar/amp and
mechanical wind-up before five seconds is retained as uncertain contamination
of the selected4.10–4.95-second interval, never asserted noise-only.

Ran seven focused checks with standard-library Python: exact role versions,
map swaps/extras/refusals, shared-author/media refusal, historical snapshot
identity, all pinned helper/runner/qualification bytes, and both independent
signal-ownership oracles. **7 PASS in0.565seconds**, exit0. This deliberately
avoids repeating the full numeric suite already passed at the previous
checkpoint; the owner separately reports21 locked-environment passes.

Read nonexecutable release suggestion SHA
`617c88c050bf913488b72cc8cc73b43c349e602134860f7ed8d23b9fc6758d45`:
authority is `PROPOSAL_NOT_EXECUTABLE`; selectors bind exact candidate
application/export receipts and NR10 same-run `restoration-manifest.json`
SHAa6c371ab rather than its mutable analysis-enriched current manifest.
The actual authority and protected/candidate runtime readback still must come
from root's exact release. This audit did not run the suggestion or comparison,
read candidate/source samples, invoke FFmpeg, or adopt any output.

Disposition sent promptly to root and owner: **positive exact2322 source
verdict; no source blocker found for root's measurement-release review**.
This authorizes no further action by this lane. Runtime comparison completion,
protected identities, delivery eligibility and operator listening acceptance
remain distinct evidence.

Receipt: `repo_patterns | frozen2322 source/3cc0 fixtures, archived snapshots,
seven inert focused checks | closed mixed-producer provenance review |
root successor source-audit delegation, R-N12/R-N13 | historical7f46 closure,
resource-qualified successor supplied | positive source verdict,7PASS;
measurement not executed, no source edits or adoption`.

## Final rational-clock guard review

Root authorized a narrow source correction after the first authorized2322
comparison reportedly refused the actual1/600-second source stream clock
before any PCM/meter work. The universal1ms ceiling was not the pinned media
packet comparator's declared rule. The first comparison failure is owner/root
reported runtime evidence, not a measurement repeated by this audit.

Exact corrected driver:
`d36b5316db5fa9fb5ce58acec1fc1213934ef60db7bfe12373eeff856eb0f529`.
Exact owner tests:
`6f46b35ad273b3432a3773787e5fdc71febed99a3a268e75eef80219d22f7222`.
Historical2322 snapshot reads back exactly. Reviewed the complete delta: it
imports Fraction, reads source/export stream time bases from their bound
manifest/export metadata, requires both positive, and requires recorded packet
tolerance equal exactly to float(max(source_tick,export_tick)). This matches
pinned media.compare_video_packets: at most one coarser rational clock tick for
mux rounding. Finite nonnegative packet delta guards still require each actual
delta≤that tolerance. It adds no arbitrary larger cap, resampling, timing edit,
profile, DSP, producer-map or timer/coverage change.

Six focused inert source tests passed in0.089seconds: actual coarse-clock
metadata with zero packet deltas accepts; fabricated20ms tolerance refuses;
actual20ms PTS shift refuses; existing20ms header diagnostic with exact packets
accepts; exact producer role/map tests and both independent signal-ownership
oracles pass. No new fixture is needed beyond those meaningful existing clock
oracles. Positive exact d36b verdict was sent promptly to root and source owner;
no source blocker found for root's new hash-bound release review.

Nonexecutable clock proposal remains a suggestion until root supplies the
actual measurement authority. This lane read no actual audio samples, invoked
no FFmpeg, reran no comparison, and changed only this durable receipt.

Receipt: `repo_patterns | frozen d36b source/6f46 tests versus archived2322,
pinned media packet-clock rule, six inert focused checks | remove invented1ms
clock gate without broadening timing evidence | root narrow guard-review
release, R-N12/R-N13 | first2322 comparison reportedly refused valid1/600clock |
positive d36b source verdict,6PASS; measurement not rerun, no DSP/adoption`.

## Explicit300-second budget successor

Root authorized only a budget successor after the second comparison reportedly
exhausted its60-second envelope at the first master meter with completed NR8
panels retained. This audit did not inspect or rerun that actual measurement;
its incomplete artifacts retain their original scope.

Read exact new driver
`dbcb63463e3c820510d01aa836b1814a1c4333f598be0f620bf56c783fd11cc3`,
owner tests
`a9436362c900615d8c4e31f38b5ba36fcc6f74b0e7e6e7b7727fa5aecb4aaaca`,
and archived prior d36b source (exact historical SHA confirmed). Entire source
delta changes WHOLE_SECONDS300/PROCESS_SECONDS295, their declared reserve
comment, and required root release `whole_job_seconds_max` exactly integer300
(refuses60, True and300.0). The fixed five-second reporting/cleanup reserve,
two threads, owned runner, closed producer map, shared DSP/native controls,
rational clocks, meter calls, early timer and partial coverage code are otherwise
unchanged. No caching or DSP redesign was introduced.

Five focused inert tests PASS in0.209seconds: budget refusal before input work,
accelerated preflight/import stalls, partial local-panel retention, existing
caller interval-timer preservation and custom-handler restoration. No actual
audio/FFmpeg comparison ran in this lane. Positive exact dbcb source verdict
sent root and owner; no source blocker found for root's separately issued300
measurement release. The nonexecutable proposal must not substitute for that
root authority, and this review does not upgrade earlier incomplete runs.

Receipt: `repo_patterns | frozen dbcb budget-only delta/a943 fixtures versus
historicald36 | verify explicit root budget and ownership preservation |
root budget-only successor release, R-N12/R-N13 | actual prior60s measurement
reportedly incomplete | positive source verdict,5PASS; no audio work/adoption`.
