# Source-bound capture profile skill design

Owner: `/root/tool_skills`. Authority: operator-authorized continued parallel
project work; repository AGENTS.md; R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13.
This assignment owns this new design document only. Existing twenty-three
skills stay frozen. Root owns worker admission, profile use, registry/recipe
activation, counts, tracker evidence, publication and actual listening acceptance.

## Definition of done before design implementation

- Read the authoring worker/hook contract and coordinate supported closed knobs,
  source hashing, interval units/bounds, review assertions, new outputs and limits.
- Require a fresh source-bound profile for its own take; never transpose an old
  capture hash or imply that matching tuning makes another recording equivalent.
- Separate verified source/metadata facts from reviewer-selected interval and
  uncertain fan/guitar/click overlap. Capture shape/floor is not measured SNR.
- Explain pure denoise/residue versus optional EQ/compression and normalization,
  supported stage contrasts and explicit experimental quality boundaries.
- Plan practical inspect/research/bounded iteration with immutable receipts,
  no arbitrary filters, implicit installation or acceptance through authoring.
- Obtain independent adversarial read-only review and record named admission
  tasks. No new skill file, registry prompt or profile execution is authorized
  by this docs-only checkpoint.

## Coordination checkpoint

Worker owner: `/root/rhythm_analysis`; hook owner: `/root/tool_hooks`.
Initial sources: CAPTURE_PROFILE_TOOL_CONTRACT.md and
RESTORATION_REFINEMENT_LANE.md. Existing source-bound captured presets remain
separate verified candidates; a new authoring design cannot make them universal
or certify that their selected opening interval contains only noise.

## Intended future skill behavior

Author a fresh profile bound to the current recording's original SHA256 and an
explicitly reviewed decoded-audio interval. Inspect current source identity,
native rate/channels/extent and audio origin; distinguish audio-relative interval
units from video/container time before applying it. Matching tuning, nearby RMS,
fan context or a copied old profile never establishes same-source noise. Reject
changed input and stale source metadata; do not change a historical hash to make
another recording pass.

Record authorization and reviewer assertions with their actual scope. A reviewed
interval may contain fan/room noise, guitar decay, near-32 Hz fundamentals,
harmonics, pick or click transients. Quiet-candidate measurements and a visible
unplayed frame are evidence for selection, not verified noise-only content. The
authoring tool must retain uncertainty and cannot authenticate that someone
listened, erase music contamination or approve the master through metadata.

Keep the complete custom nine-string context without a blanket high-pass,
mains/blade notch or speech-denoiser default. Band-shape sampling and a separately
specified absolute floor are different controls; neither is measured SNR.
Reduction amount is not a guaranteed output noise improvement. Inspect native
capture/sample bounds and profile hashes before whole-take use; retain private
preroll/guard/latency receipts if the worker applies shape from sample zero.

Authoring, capture measurement, actual rendering and acceptance are separate
states. A new profile file does not prove that denoising ran or that whole-take
attacks/tails are preserved. Keep pure `denoised.wav` and source-minus-denoise
`residue.wav` distinct from optional EQ/compressor `processed.wav` and normalized
`cleaned.wav`. Pure residue cannot certify later-stage fidelity. Stage-level
attenuation bounds do not qualify total chain changes; EQ phase and gain-envelope
effects remain explicit.

## Closed controls and contrast design

Final tool/CLI, fields, units/defaults and ceilings await the authoring worker
handoff. Expose only validated typed controls: current-source identity/reviewed
interval, finite bounded denoise controls and any explicitly admitted closed
stage preset. No arbitrary filters, shell/argv, URL, full profile object, hidden
gain makeup, time stretching or automatic profile transfer should enter the hook.
Require fresh local output/profile paths with original-component traversal and
symlink rejection; retain input/profile hashes and compact receipt pointers.

A planned custom-profile workflow must describe how profiles become callable:
authoring a file alone does not extend the current named denoise enum. Root/hook
owners must admit a fixed profile-use path or another explicit typed operation.
The existing benchmark's three profiles remain separate; source-bound capture
profiles cannot silently run on synthetic or unrelated sources.

For iteration, inspect measured opening/pause evidence and uncertainty, choose an
authorized interval, author a bounded candidate, then compare one supported
control or stage in fresh outputs at matched loudness. Preserve bypass, pure
denoise and optional processing contrasts. Keep the interval and all unchanged
settings fixed during a single comparison; record why changing capture is a new
candidate rather than silently rebinding prior evidence. Research actual FFmpeg
capture/floor/EQ/compressor controls through
[the refinement contract](RESTORATION_REFINEMENT_LANE.md).

No accepted best tone, transparent preservation, identified fan-only content,
measured SNR, corrected rhythm or listening acceptance follows from a profile
being valid. The authoring skill should abstain on unsupported claims while
continuing permitted bounded metadata/profile work.

## Named admission tasks and adversarial review

1. `capture-profile-worker-contract` — restoration owner supplies implemented
   fixed CLI, supported knobs, fresh output/review/source binding and budgets.
2. `capture-profile-use-contract` — root/hook owners define explicitly how a new
   source-bound profile is rendered without arbitrary JSON/filter dispatch.
3. `capture-profile-hook-contract` — hook owner locks validated typed fields,
   compact result/error keys and source/path/resource rejection behavior.
4. `capture-profile-skill-forward-review` — independent read-only review covers
   old-profile transplant, fan/guitar overlap, units, floor versus SNR, purported
   best tone, and residue versus later-stage damage.
5. `capture-profile-skill-admission` — root assigns a new skill after meaningful
   generated success/rejection and actual bounded capture evidence; exact bundle,
   prompt/schema proof and publication are subsequent separate checkpoints.

Open questions: exact source input/SHA contract, reviewer metadata fields and
assertion scope, interval units/limits, closed stage presets, absolute floor and
reduction bounds, authored-profile use/admission, output root and failure keys.
No new catalog or prompt is claimed by this docs-only design.

## Restoration-owner proposal checkpoint

The owner proposes `capture_profile` authoring from current INPUT, its verified
source-run `source.wav`/manifest and an exact source-bound review JSON. This is
still a proposal, not an implemented CLI or callable hook. Fresh original-source
hash is computed; old source SHA or shape is never transplanted. Authoring is
metadata/profile work with no DSP, decoding, model or default separation.

All denoise controls would be explicit: reduction 0.01–12 inclusive, floor −80 to −20,
adaptivity 0–1 and integer gain smoothing 0–50, without universal numeric
defaults. Integrated loudness −70 to −5 LUFS and true peak −9 to 0 dBTP are also
required explicit controls, with no defaults. All numeric endpoints are inclusive
except EQ frequency must remain strictly below native Nyquist. Capture is
0.1–10 seconds inside native extent. EQ/compression are
absent by default. Any admitted EQ is bounded to three bands, 160–6,000 Hz below
Nyquist, ±3 dB and Q=0.5–2. The five-field compressor is bounded to threshold
−36 to −6 dB, ratio 1–3, attack 8–20 ms, release 60–200 ms and knee 0–6 dB,
with fixed 25% wet and no makeup gain. These numbers are proposed closed schema
limits, not recommended settings or enforced runtime facts yet.

Proposed immutable outputs are source-run `capture-profiles/<id>/` artifacts
with source/PCM/manifest/context/settings hashes. Existing render-scoped
authorization permits `profile.json` and `receipt.json`, status
`authored_unrendered`; profile-authoring-only scope produces nonrunnable
`proposal.json`, proposed status `draft_authorization_incomplete`. It must not
set `noise_capture_authorized:true` or promote authority while authoring.
These branches preserve already-existing authorization, not a recurring user
confirmation flow. Review status, authorization, selected-by/reviewed-by remain
supplied assertions. Declared present music/click content would reject
selection; unknown content retains uncertainty rather than becoming noise-only.
Articulation/artist references are context, never automatic EQ or score targets.
Custom profile application still needs its own admitted typed route; the six
existing denoise names remain frozen.

The fixed proposed CLI is `capture_profile.py INPUT --run-dir RUN_DIR
--capture-start SEC --capture-end SEC --reduction-db NR --noise-floor-db NF
--adaptivity AD --gain-smooth GS --integrated-lufs LUFS --true-peak-dbtp DBTP
--review REVIEW_JSON`. Canonical proposed MCP interval fields are
`capture_start_seconds`/`capture_end_seconds`. Optional EQ maps to at
most three fixed numeric `--eq FREQUENCY_HZ GAIN_DB Q` triples; compression has
five all-or-none fixed numeric flags. Bounded array/object schema validation is
a specific hook admission task, not already supported by the strict validator.

The proposed review sidecar is a regular nonsymlink file under the run, at most
16 KiB. Version 1 rejects unknown keys and binds live original-source, manifest
and source-PCM hashes plus exact native-sample-converted interval. Fixed time
axis is `decoded_source_audio_samples`. Selected/reviewed identities, authorization
reference and note are bounded supplied assertions. Review states are
`reviewed_candidate|reviewed_possible_contamination|rejected_contaminated`;
authorization scope is `profile_authoring|experimental_capture_render`.
Music/click status is `unknown|suspected|reviewed_no_obvious_content|reviewed_present`;
whole-take ambient music is separately
`not_reported|suspected|reviewed_absent|reviewed_present`. None authenticates human
identity/listening or proves noise-only content.

Rejected contamination or declared present capture content would return
`needs_reselection` with no runnable profile. Unknown/suspected content retains
uncertainty under supplied authorization. Suspected/present whole-take ambient
music needs its separately explicit task before DSP; no silent separation occurs.
Direct `media.py clean INPUT PROFILE_PATH` can be part of a later admitted use
workflow, while the existing MCP remains fixed named profiles only.

## Design review checkpoint

Independent eight-case read-only review found no concrete instruction gap:
source-hash transplant refused, unknown fan/guitar overlap retained, floor not
SNR, authoring not rendering, and pure residue not full-chain fidelity. See
[the reviewer-owned dated receipt](../agent-notes/2026-10-05-agent-iteration-skill-review.md).
New hook proposal details above remain future and need worker qualification;
no existing skill or callable catalog was changed. Exact output/error ceilings,
new-worker endpoint/authorization-branch tests and profile-use admission remain
named open tasks. The lower reduction endpoint was locked inclusive with both
owners, but a draft contract is not yet runtime proof.

## Root worker admission and skill implementation DoD

Root admits the qualified capture-profile worker for tool twenty-five after
thirty-three passing tests and authoring qualification. The previous design-only
hold is superseded for this authoring primitive, while profile application/DSP
remains a separate route. This lane now also owns new
`.agents/skills/guitar-capture-profile/SKILL.md`; existing skills stay unchanged.

Before creation: read the final worker's fixed controls, sixteen-field review,
hash/native-header checks and three status branches. Describe no DSP, learned
shape, new decode, audible master or listening acceptance. Preserve existing
authorization without escalation or needless recurring confirmation. Validate
bundle structure and independent adversarial behavior, then all twenty-five exact
initialized MCP prompts/schema once the hook is activated. Root owns actual-take
authoring, later rendering, tracker evidence and publication.

## Implemented skill checkpoint

The new skill reflects required explicit capture/control/loudness/peak settings,
closed optional EQ/compressor objects and timeout 1–60/default 60. It records
exact source/manifest/native/review bindings and preserves supplied review/scope
assertions separately from verified file/header identities. Byte hashing reads
media/PCM; no payload decode or learned shape is performed. Unknown audio origin
remains null. Existing capture-render authorization persists without another
confirmation; authoring-only scope is never promoted.

The skill distinguishes `authored_unrendered` profile, nonrunnable
`draft_authorization_incomplete` proposal and `needs_reselection` receipt, and
explains that successful dispatch does not mean audible rendering or acceptance.
Custom application remains separate from the fixed denoise enum. Bundle
validation and direct CLI help pass. Independent behavior review, linked current
contract status, final worker audit corrections and exact twenty-five-tool MCP
readback remain pending before the final handoff.

## Twenty-five-skill interface proof

At 2026-10-06 00:31 UTC, all twenty-five repository skill bundles pass the
bundled skill-creator validator. An initialized actual stdio MCP session returns
twenty-five tools and prompts; every `prompts/get` text exactly matches its
current `SKILL.md`. Capture authoring exposes fourteen closed properties,
eleven required fields, explicit finite control bounds, timeout 1–60/default 60,
at most three closed EQ bands and the exact five-field compressor object.
The new skill SHA256 is
`f1a795cce3622739eddd8d4541cc306c98782e186f9e205621783d8449efbc72`.

Independent instruction review passes source transplantation, capture overlap,
floor/SNR distinction, authorization scope, outcome interpretation and
authoring/render/listening separation. Its live unknown-field call rejects
before worker execution. Existing twenty-four skills remain unchanged by this
assignment. These are interface and instruction proofs, separate from callable
worker qualification: the worker owner's minimum-interval floating-point and
huge-integer audit repairs still await final freeze/readback. Root owns actual
source authoring, subsequent profile application and publication.

## Repaired worker and refreshed skill proof

The worker owner freezes capture authoring SHA256
`7d2820878826c87aabf2ab60b73c997b9d406b7f3ff8943d6012ed967444c355`
after forty-five passing tests (thirty-three original and twelve audit cases)
and an independent same-source pass. The minimum/maximum capture duration uses
integer native sample counts. A boundary-only profile-seconds encoding change
leaves the end and native sample bounds unchanged; receipts retain requested
seconds, exact native samples and profile seconds separately. Oversized numeric
controls now reject with a bounded domain diagnostic. These worker test results
are owner-reported; this lane independently verifies the frozen source hash.

The skill includes that interval distinction. Refreshed bundled validation and
initialized actual stdio proof pass all twenty-five tools and exact skill
prompts. Its final SHA256 is
`33cd07d572c653222233e17d935bc589a11dbd32cd76def6d46128c7d65b268e`.
The typed schema remains fourteen closed properties and eleven required fields.
The hook owner's actual minimum-boundary test and final independent reviewer
receipt are separate pending checkpoints; no actual source authoring, DSP,
master acceptance or source publication is claimed here.

## Final hook qualification checkpoint

The hook owner closes its actual initialized MCP boundary test on the same
frozen worker: capture 0.2–0.3 seconds with reduction 0.01 emits native bounds
3,200–4,800, and the authored profile passes the frozen media profile validator.
No DSP occurs. All six focused hook tests pass; the linked contract now records
current authoring admission and the closed boundary qualification. The broader
hook suite remains its owner's separate verification lane. This skill's final
bundle, schema and exact prompt proofs are complete. Actual source authoring,
custom application, audio quality and publication remain root-owned evidence.

Independent final review is closed in
[the reviewer receipt](../agent-notes/2026-10-05-agent-iteration-skill-review.md).
The reviewer repeats the final exact capture prompt and twenty-five-tool
catalog, checks fourteen properties/eleven required fields, and observes
structured rejection of unknown fields and huge integers before worker launch.
It finds no new source, authorization or claim gap. Worker-owner test results
and the hook owner's actual boundary proof remain explicitly attributed.
