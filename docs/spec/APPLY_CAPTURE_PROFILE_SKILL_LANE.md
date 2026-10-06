# Capture-profile application skill design

Current checkpoint: root admits the local typed application route after native
generated-fixture qualification and the application-only supervisor's inert
actual MCP timeout proof. The skill lives at
[guitar-apply-capture-profile](../../.agents/skills/guitar-apply-capture-profile/SKILL.md).
Positive generated-native rendering through the new MCP route, actual-take
quality, publication and listening acceptance retain separate evidence. The
twenty-seven original skills remain untouched. Earlier docs-only/source-draft
checkpoints below are historical.

Owner `/root/tool_skills`; restoration owner `/root/rhythm_analysis`; hook owner
`/root/tool_hooks`. Authority: root's explicit docs-only assignment, persistent
operator-authorized full-take capture processing, repository AGENTS.md and
R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13. Own this new document only. Current
twenty-seven skills/catalog are frozen; this design creates no skill, prompt,
recipe, registry contract, render, inference or installation.

## Definition of done before design implementation

- Coordinate the fixed application inputs, pinned authoring receipt, same-source
  parent/native capture binding, supported controls, fresh outputs and budgets.
- Draft decision-useful intent/dependencies, source/contamination checks, stage
  interpretation, bounded research/iteration and acceptance instructions.
- Preserve existing capture-render authorization without inventing a repeated
  approval question, authenticating assertions or promoting authoring-only drafts.
- Explain whole-take preservation of near-32 Hz guitar, native rate/channels,
  sample extent/source origin and timing; structural checks do not accept tone.
- Keep pure denoise/residue separate from optional EQ/compression, normalization
  and delivery encoding. Retain failures and prevent silent master adoption.
- Distinguish verified precommit failure from interruption after atomic candidate
  publication. Transport timeout alone cannot establish candidate absence;
  inspect bounded source-bound receipts before retrying or declaring an outcome.
- State planned versus actual interface evidence. Lock exact caps/summary/errors,
  qualify worker/source and obtain root admission before a tool28 skill or prompt.

## Coordinated interface proposal

Proposed tool is `apply_capture_profile`; a matching future skill/prompt is
subject to root admission. The worker owner's fixed proposal is:

```text
python3 scripts/apply_capture_profile.py INPUT --authoring-dir DIR
  --receipt-sha256 SHA [--timeout-seconds INTEGER]
```

Proposed closed MCP fields are required `input`/`authoring_dir` strings
1–4,096 characters and `receipt_sha256` exactly 64 lowercase hexadecimal
characters, plus proposed outer MCP integer `timeout_seconds`
12–600/default 600. The proposed wrapper passes an inner worker budget ten
seconds smaller, at least two seconds; this mapping is not yet implemented or
admitted. The direct CLI independently accepts 1–600/default 600 work seconds
plus bounded exceptional cleanup grace. Hash
syntax requires explicit wrapper validation rather than an unsupported schema
pattern keyword. Input is
the exact current original named by the parent baseline. Authoring directory
is an explicitly selected `RUN/capture-profiles/ID/` under repository
`artifacts/runs/`, containing its own `profile.json` and `receipt.json`. Receipt
SHA comes from the previous tool25 result, not discovery of the newest file.
Literal paths reject traversal/symlink components, URLs, backslashes and
dot/staging components before normalization. These are agreed design fields;
live validator/dispatcher admission remains separate.

No `output`, candidate name, executable, filter string, model/runtime,
profile-JSON object, source-hash override or new DSP setting is a caller knob.
The worker allocates a fresh immutable candidate automatically. All reduction,
floor, smoothing, loudness/peak, EQ and compressor settings come only from the
pinned authored profile. This application operation does not widen the six
named `denoise` presets or change their contracts.

## Intended skill instructions

**Intent and dependencies.** Apply one existing authored source-bound capture
profile to the complete original through the existing restoration/export chain,
producing a separate unreviewed candidate. Use the current source/native baseline
and tool25 authoring result first. Read the authoring receipt's status and exact
scope; authored settings alone are not prior noise measurement or rendering.
No graph scheduling, auto profile selection or master adoption is implied.

**Inspect before DSP.** Verify the freshly computed original identity and exact
baseline path; parent manifest/native `source.wav`; profile and pinned receipt;
review, instrument/capture context, settings and authoring/validator producer
hashes. Recheck identities before publication. Require no-time-stretch mapping,
explicit finite source-audio origin, native header/rate/channels/sample count and
exact capture bounds. Receipt requested/profile seconds and native samples must
agree; the authoring boundary-only float encoding must never move a sample.
Original-to-PCM decoder history is retained metadata, not authentication of
capture content or physical synchronization.

**Scope and contamination.** Only `authored_unrendered` with existing supplied
`experimental_capture_render` scope/reference is eligible. Draft/reselection
receipts cannot render; do not edit status/hash/authorization fields to bypass
this. Use existing session authority faithfully when a fresh authoring operation
is needed, without asking again merely to populate a sidecar. Supplied reviewer
identities and authorization are assertions, not authenticated approvals.
Rejected or reviewed-present capture music/clicks requires reselection.
Unknown/suspected fan, sustain, guitar or metronome overlap stays uncertain.
Ambient music does not silently authorize separation, a speech denoiser or a
different model. Similar tuning or RMS never permits another take's capture.

**Whole-take processing and preservation.** The proposed worker reuses existing
captured-shape preroll, calibrated denoiser-delay compensation, native restoration
and export functions. Apply from original sample zero without trimming or time
stretching; retain capture interval/native sample map and actual processing
settings/versions. Preserve near-32 Hz low-string fundamentals, intentional
saturation, pick attacks, palm mutes, rests, tuplets, tapping, sweeps, legato and
sustain. No blanket high-pass/hum notch, artist-derived automatic EQ or assumed
noise-only floor is justified. Capture shape and explicit absolute floor are
different controls; neither is measured SNR or transparent-noise-removal proof.

**Read the stages.** `denoised.wav` is pure pregain denoise;
`residue.wav` is source-minus-pure-denoise. Optional `processed.wav` applies the
authored EQ then compression. `cleaned.wav` normalizes processed audio when
present, otherwise pure denoise; `baseline.wav` supplies the matched-target
comparison. Delivery export/codec changes are separate from PCM master evidence.
Pure residue cannot certify EQ/compressor/normalization fidelity. Native sample
count and measured delay do not establish complete acoustic or physical A/V
alignment; EQ phase and attack/sustain envelope changes remain explicit risks.

**Results and abstention.** A proposed successful result is
`rendered_unreviewed`, evidence `source_bound_capture_profile_application`, with
fresh candidate manifest/application receipt/export paths and hashes, native
capture bounds, `dsp_performed:true`, `listening_accepted:false` and
`master_adopted:false`. Capture retains requested/profile seconds, native samples
and source-media span. Export retains status, audio master, nullable video and
outcome path/hash; audio-only input cannot claim video verification. Require
completed input rechecks, native extent/timeline and export verification before
calling it a structural render success. A verified failure before atomic commit
produces no committed candidate and cleans only owned staging. If publication
already committed and reporting then fails, the candidate remains separately
recoverable, unreviewed and unadopted; report interruption does not erase it or
invalidate completed render checks. Never infer listening approval, good tone,
noise-only removal or intended-note/rhythm correction from a successful call.

Interpret the worker's publication state separately from its nonzero exit:

| Observation | Result status | `candidate_publication` | Recovery fields |
|---|---|---|---|
| Verified precommit failure | `error` | `not_committed` | Both candidate objects null |
| Commit confirmed, reporting interrupted | `committed_unreviewed_reporting_interrupted` | `committed_unreviewed` | `committed_candidate` contains pinned recovery selectors |
| Publication attempted but outcome unobservable | `publication_outcome_unknown` | `unknown_after_publish_attempt` | `committed_candidate` null; `possible_candidate` contains prepared selectors |

Failures remain exit 2 and unaccepted/unadopted. A `possible_candidate` describes
prepared identities, not proof that its directory exists or committed. Both
canonical recovery objects use schema 1/status `rendered_unreviewed`, `run_dir`,
source/profile/authoring-receipt SHA256s, plus exact `manifest`, `receipt` and
`export_outcome` objects containing SHA256 and fixed relative paths
`manifest.json`, `application-receipt.json`, `export/outcome.json`. Listening and
master-adoption fields remain false. Do not promote the nested prepared status
into observed publication.

Durable failure states distinguish `failed_no_candidate_published`,
`failed_reporting_committed_candidate_retained` and
`publication_outcome_unknown`. A written 64 KiB failure receipt retains full
confirmed success metadata or prepared recovery identities and owned events;
failure-receipt path/hash can be null when preservation itself fails. Missing
failure metadata is not absence or cleanup proof.

Transport timeout, missing stdout or a disconnected client leaves commit outcome
unknown until bounded receipt/hash inspection establishes it. Inspect the exact
worker-retained source/profile/authoring and candidate selectors, not a newest
run or a broad media search. Confirm manifest/application/export identities and
commit state before claiming absence, treating a recovery as accepted, deleting
artifacts or repeating a full render. Failure status, cleanup proof, committed
candidate existence and listening acceptance are separate facts. These fields
are observed prototype semantics; typed-tool availability and containment still
require root admission.

**Research and bounded iteration.** Inspect capture uncertainty and source
receipts; research actual controls through
[the restoration contract](RESTORATION_REFINEMENT_LANE.md) and its primary
sources. Change settings through a new tool25 authored profile and pin its new
receipt, then apply that candidate in a fresh run. No direct application override
is supported. Hold source/capture fixed while varying reduction first; compare
absolute floor or smoothing separately. Keep EQ/compression off for a pure
denoise contrast, then add supported stages as separate contrasts. A changed
capture is a new source-bound proposal, not a silently rebound old profile.
Prefer a small first comparison set and record settings, hashes, versions,
commands, confidence and failures. This workflow preference is not an invented
approval gate or an enforced worker trial cap.

Compare native low-register/band and quiet/active passage measurements alongside
matched presentation level, loudness mode, peak and local attack/tail behavior.
Audition source-aligned palm mutes, fast passages, sustained tails and ending
legato/tapping; report what was actually heard. Equal whole-take LUFS or high
coherence does not guarantee equal passage gain, preserved articulation or best
tone. Musician listening selection and master acceptance remain explicit later
states; preserve original, parent run, profile, current master and latest pointer.
Do not adopt a candidate or export new annotations as confirmed errors implicitly.

## Proposed budgets and admission checkpoints

Current worker proposal bounds original <=3 GiB, native PCM <=1 GiB,
8–192 kHz/mono or stereo/<=300 seconds, direct worker 1–600/default 600 work
seconds plus at most five seconds of exceptional cleanup grace, and
existing media thread count two. The application cap is narrower than tool25's
authoring extent; a valid long profile does not make unsupported rendering valid.
All validation precedes media subprocess launch. Owned private
`artifacts/.capture-apply-…` staging remains unpublished until checks pass, then
one fresh run publishes atomically. Root owns final owned-child timeout/cleanup
qualification. Agreed design JSON limits are profile and review 16 KiB,
manifest 1 MiB, contexts 64 KiB, authoring/application receipts 64 KiB and compact/
domain result 16 KiB. Proposed failures return bounded schema/tool/publication-aware
diagnostic JSON with code/message and exit 2; parser errors remain nonzero stderr. Combined
diagnostics preserve exact recovery identities and attempt to include the last
eight process events. If the full object exceeds 16 KiB, the event tail becomes
empty with `owned_process_events_omitted:true`; absence of compact events does
not mean no subprocess action occurred. A written durable failure receipt
retains the full bounded trace. A future
deliberate dispatcher extension must preserve the fixed domain diagnostic with
`isError:true` without changing other tools.

The owner refines the proposal to owned POSIX subprocess sessions, live PGID/SID
checks before group signals, 4 MiB file-backed stdout/stderr ceilings and at most
128 process receipts. Process inspection is bounded to one second. All cleanup
shares one absolute five-second deadline rather than receiving five seconds
per child/action; protected exceptional cleanup grace is separate from nominal
work. These ceilings are not hard real-time guarantees. A leader exit does not
establish descendant absence.
Inspection/cleanup failure retains `cleanup_failed`; direct-child termination
and reaping cannot prove that unknown descendants are gone. Postvalidation
failures retain bounded `artifacts/application-failures/ID/receipt.json` outside
discarded private audio, with source/profile/authoring pins and at most eight
process events in compact diagnostics. Do not infer cleanup from a deadline
setting or a terminated transport. Exact recovery fields are recorded above;
native/outer-containment qualification remains separate. No-candidate language
applies only to failures verified before atomic publication.

Proposed MCP timeout is outer 12–600/default 600 seconds with a fixed ten-second
headroom and inner budget `outer - 10`, minimum two seconds. It accommodates
the nominal work and shared exceptional cleanup proposal without exposing a
new grace/cleanup knob. The budget mapping is proposed, not implemented or
measured runtime containment. Future MCP timeout containment needs separate
proof: the worker's FFmpeg child
sessions differ from the existing wrapper's process group, so killing the
wrapper group does not establish that those children stopped. Lock the inner
worker budget and outer cleanup slack or qualified worker SIGTERM handling,
then exercise an actual owned-tree MCP timeout fixture before admission.
Standalone alarm/child-session cleanup and outer wrapper containment are
different evidence; no observed leak or absence is inferred here.

The initial design checkpoint recorded twenty owner-reported
metadata/mocked-processing tests while extra audits continued. The corrected
source qualification below supersedes that checkpoint. These are fixture/prototype results, not
actual-take rendering or typed-tool admission. Existing media functions, authoring
worker `7d282087…`, presets, twenty-seven contracts and masters remain unchanged.

Named next checkpoints: `capture-application-worker-freeze`,
`capture-application-native-export-qualification`,
`capture-application-inner-outer-timeout-qualification`,
`capture-application-closed-hook-contract`,
`capture-application-skill-forward-review`, and
`capture-application-root-admission`. Only after those supported contracts are
concrete and root releases this lane should the actual new skill be created,
validated and exactly read back with the live catalog. Existing user full-take
processing authorization persists; these engineering qualification checkpoints
are not new operator permission requirements.

Design sources: [application prototype](APPLY_CAPTURE_PROFILE_LANE.md),
[authoring workflow](CAPTURE_PROFILE_WORKFLOW_LANE.md),
[authoring tool contract](CAPTURE_PROFILE_TOOL_CONTRACT.md) and
[agent evidence contract](AGENT_TOOLS.md). Source/provenance checks, DSP completion,
generated quality, export identity, review observation, audition choice, real
master acceptance, AU/Logic and native editor compatibility remain separate.

## Design readiness and independent review

At the initial design checkpoint, the hook owner supplied
[the exact proposed application contract](APPLY_CAPTURE_PROFILE_TOOL_CONTRACT.md),
SHA256 `9f2749a875c1a91a4171e6d5f9b0fab1f708c5a177735eab9cb9e5ed95f64194`.
Its path/hash/deadline fields, JSON limits and compact success/domain error
semantics were design values, not admitted runtime guarantees. The current
corrected contract and qualification are recorded below.
Application summary requires export status/master/nullable-video/outcome identity;
audio-only evidence remains explicit. Current worker/native/export/deadline
qualification is still root/owner work.

Independent read-only forward review finds no concrete instruction gap in pinned
source/receipt/scope binding, persistent authorization versus draft/reselection,
unknown capture content, stage/residue fidelity, native/full-take timing,
unreviewed fresh outputs and re-authoring for supported comparisons. It performs
no file edit or execution. Linked documents resolve and whitespace checks pass.
Readback confirms the catalog remains twenty-seven and no application skill
directory is created. Only this new design file changes in this lane.

The bounded skill content and concrete proposal coordination are ready. Root's
future release, supported frozen worker and meaningful runtime checks must precede
actual skill/tool admission; no tool28 availability, render, audio approval,
installation, inference or publication is claimed by this design.

## Root-directed postcommit reporting correction

Root's readback of prototype `31eafcc8…` found that a reporting interruption
after atomic publication could falsely claim no candidate. The owner repairs
that outcome classification and bounded recovery selectors. This skill design
now explicitly separates verified precommit no-candidate failure from an
existing committed unreviewed/unadopted candidate, and transport timeout from
verified absence. Original, parent, profile, current master and latest pointer
preservation remain required; existing authorized processing scope persists.
At this correction checkpoint, status/selector names and new source qualification
were pending owner freeze; the final correction is recorded below.
This correction changes only this new design file; no actual skill, catalog,
live hook, native fixture or audio operation is admitted or executed here.

Independent read-only review of this narrow correction finds no concrete gap:
precommit absence, committed recovery and transport-unknown outcomes remain
distinct; source-bound receipt inspection precedes retry/deletion/acceptance;
inner/outer containment proof, originals/latest preservation, listening-false
state and existing scope remain explicit. No file edits or execution occur in
that review. Links and whitespace checks pass and catalog readback remains
twenty-seven. That guidance correction completed while exact recovery field/status
names and repaired-worker qualification were still with their owners.

## Corrected source and current design checkpoint

Current source readback verifies worker SHA256
`00a03ef9fad8543be4335cb5cbcd3c9d9580a6b40b8faeb826811b105fd5daa6`
and draft tool-contract SHA256
`57f4133c1d61701a71241c9ccacd9c7ac219a4987e0732745d2c1b859a806190`.
The restoration owner reports forty-six combined fixture/audit tests passing in
26.087 seconds for this source. This lane does not rerun those tests or claim
native media proof. Historical `31eafcc8…` prototype evidence remains attributed
to its earlier owner/root checkpoint; its source archive is unavailable here,
so no independent old-to-new source diff is claimed.

The publication table and canonical selectors above now reflect the frozen
correction. Confirmed commit, confirmed precommit failure and an unobservable
publish attempt have distinct states. A prepared object's nested
`rendered_unreviewed` status cannot establish publication. Compact success and
combined diagnostic output are each bounded to 16 KiB; complete durable
application/failure receipts are bounded to 64 KiB. Event-tail omission retains
the exact recovery selectors and is explicit. Standalone worker work seconds
remain separate from its shared exceptional cleanup grace and the proposed MCP
outer-to-inner budget.

The proposed MCP outer range 12–600/default 600 yields inner range
2–590/default 590 with fixed ten-second headroom. This is a contract proposal,
not an implemented timeout proof. Native/export qualification and an actual
owned-tree MCP timeout fixture with distinct child sessions remain prerequisites
to root admission. Current twenty-seven tools/skills remain unchanged; no tool28
skill, render, inference, installation or listening/master adoption is created
by this design update.

Independent read-only closure review against current `00a03ef9…` source, owner
lane and corrected draft contract finds no concrete instruction gap. It checks
the three publication states, prepared versus observed identities, diagnostic/
durable caps, event omission, direct versus proposed MCP budgets, distinct-session
timeout proof requirement, persistent authority and unadopted preservation.
The reviewer performs no file edit or worker/tool execution. Local link and
whitespace checks pass; catalog readback remains twenty-seven and no application
skill directory exists. The bounded design content is ready for root's later
runtime qualification and admission decision.

## Released skill-source draft

Root separately releases the new skill draft after independent generated-native
qualification; this lane does not rerun native processing. The draft's bounded
instructions reflect the four-field proposal, exact parent/source/native/profile
binding, existing render authority, pure-denoise versus optional-stage evidence
and all three publication recovery classes. The bundled skill validator, local
links and whitespace checks pass. Independent read-only forward review finds
no concrete instruction gap and performs no edits or worker/tool execution.

Typed application-only supervisor proof, source freeze and root admission remain
pending. Final all28 validators and actual initialized MCP exactprompt readback
are scheduled after that freeze; source skill creation is not catalog availability
or listening acceptance. All twenty-seven existing skill files remain untouched.

## Local typed-route qualification checkpoint

Root/hook-owner admission releases the local twenty-eighth route with unchanged
four-field schema, fixed inner work budget and fallback boundary. The hook owner
attributes twenty-three adapter tests and three independent tests to frozen
supervisor `ea2d…`, and seven focused typed-route tests to local integration.
Current pinned application worker is `790ac58f…`; its owner reports fifty-one
worker tests in 36.149 seconds. Earlier `00a03…` source results remain historical.
This skill lane does not execute DSP or promote inert-session observations into
kernel containment. Positive generated-native MCP application and actual-take
listening are separate from these source/timeout proofs.

Independent final skill review finds no behavioral instruction or evidence-scope
gap. Its linked-contract coherence finding is sent to the hook owner: older
proposal blocks must be distinguished from current local admission. The final
skill adds explicit inline worker-diagnostic omission semantics, retaining
pinned durable results and canonical publication recovery.

A first bulk stdio proof using the host-default interpreter times out without
completing exact readback; it is not a passing proof. Process escape-hatch
receipt: actor `/root/tool_skills`; target owned readback MCP child PID 80529,
parent 80511, exact live command/parent verified; reason prolonged read-only
proof after its 45-second timeout; authority R-N11 / R-HOOK-CONVERGENCE-20261004;
prior state sleeping child with same recorded identity; action direct SIGTERM
only to that child; result original proof exits with `TimeoutExpired`. No other
session/group is signalled. The traceable alternative uses locked `.venv/bin/python`
and owned temporary file-backed protocol I/O, with no tool calls, DSP or inference.
All twenty-eight validators and exact initialized prompts pass on that alternative;
stderr is empty. The final source prompt recheck follows the diagnostic wording
update; unavailable proof is never substituted by an inferred pass.

Final same-source recheck: all28 bundled validators and local skill links pass;
actual initialized MCP returns all28 skill texts exactly with empty stderr and
zero tool calls. Application skill SHA256 is
`3b2db2abc63d9a94bc0ea1a70efa74f8118156708d523d7a35fc4cd43eac44ef`;
ordered catalog skill digest is
`ecef703213cb416cbd0363baaf2a3f942ac8b5c5365de22cdca1245cb7001258`.
Whitespace checks pass. These are validator/prompt proofs, not another render,
actual-take quality, listening, master adoption or remote publication.

Subsequent hook-owner evidence reports positive generated-eight-second actual
MCP application in 42.8608 seconds, candidate
`20261006T035515Z-75c5fae6be12`, with five native output hashes matching its
qualified `790ac58f…` standalone fixture. This is attributed hook-owner evidence,
not processing performed by the skill lane or operator-take/listening acceptance.
The skill text/hash and all28 prompt proof above remain unchanged.
