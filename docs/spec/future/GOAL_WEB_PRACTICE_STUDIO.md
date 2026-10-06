# Queued goal: local guitar practice studio and future web workflow

Status: **PROPOSED / QUEUED, not activated**. Root owns future goal activation,
Linear placement and implementation. This durable file does not create a second
unfinished goal. Current ten-hour work continues to its original 06:49:34 UTC
horizon. Future milestones have no committed dates. Authority is the
[exact operator prompt](../../agent-notes/2026-10-06-future-practice-studio-prompt.md).

### Actual tracker checkpoint — October 6, 2026

Root created [TIN-5546](https://linear.app/tinyland/issue/TIN-5546/future-goal-private-guitar-practice-studio-mastering-and-explainable)
in **Backlog**, four future milestones, and six Backlog children:
UI/TIN-5547, CORPUS/TIN-5548, IDS/TIN-5549, JOBS/TIN-5550,
STACK/TIN-5551 and HOST/TIN-5552. Scoped descriptions were appended to existing
TONE/TIN-5487, ANNOT/TIN-5489, CAP/TIN-5493 and RELEASE/TIN-5492;
those writes do not establish implementation or acceptance.

STAFF and MODEL ticket creation and complete independent tracker readback remain
pending. An authentication interruption (401), followed by a 429 rate limit
reported as 2,500 requests/hour, interrupted root's publication. The
[durable mutation receipt](../../agent-notes/2026-10-06-future-linear-publication.json)
preserves returned IDs and its earlier authentication-interruption status;
successful mutation responses are distinct from complete readback. Root owns
the retry. This future goal remains queued and unactivated; budgets, current
goal horizon and definition of done are unchanged.

Objective: turn a phone/Photo Booth take into a reproducible, fuller-sounding
practice clip with understandable source-timed feedback, editable human issue
annotations, bounded agent controls and a practical upload→process→review→iterate→
download path. Preserve nine-string fundamentals near 32 Hz, intentional distortion,
attacks, palm-mute weight and tails. A loudness-compliant export is not accepted
mastering. The latest thin/nasal/low-end feedback makes stage-attributed, matched
A/B tone review the first product priority.

## Current product versus proposed scope

Current surfaces are local HTML evidence/review pages, source-time playback,
CLI/just workflows and typed MCP tools/skills. The generic NR8 inventory contains
180 markers/eight kinds; the marked preview selects24/six kinds and composes25
callouts, with six selected markers fully suppressed and retained in metadata.
Current review categories/states are narrower than the proposed issue ontology;
accepted_observation is not a confirmed musical mistake. This is not a hosted
upload/job service or score transcription product. Exact inventories and source
receipts live in the six designs below; counts qualify their recorded artifacts.

| Design lane | Owned specification | Main decision |
| --- | --- | --- |
| Mastering | [MASTERING_AND_CAPTURE_RESPONSE.md](MASTERING_AND_CAPTURE_RESPONSE.md) | Separate pure denoise, EQ/dynamics and delivery; matched comparison before adopting fuller tone |
| UI | [WEB_UI_DESIGN.md](WEB_UI_DESIGN.md) | Improve existing local review first; one bounded web vertical slice later |
| Backend | [WEB_BACKEND.md](WEB_BACKEND.md) | Source/artifact IDs, durable bounded jobs and recovery; private single-host pilot before hosting |
| Overlays | [OVERLAYS_AND_ANNOTATIONS.md](OVERLAYS_AND_ANNOTATIONS.md) | Compact section/phrase+BPM+brief issues; human assertions and detector hypotheses retain distinct bases |
| Capabilities | [CAPABILITIES_AND_REPO_EVOLUTION.md](CAPABILITIES_AND_REPO_EVOLUTION.md) | Shared units/defaults/resources/provenance, incremental adapters and docs; no broad rewrite |
| Classification | [AUDIO_CLASSIFICATION.md](AUDIO_CLASSIFICATION.md) | Source-bound labels/heldout grouping before retrieval, calibration or larger models |

## Priorities and proposed completion evidence

**Now:** keep actual restoration/reference work moving; bind thin-tone feedback to
exact stages/candidates, preserve source/master/history, and import 404 intended
clicks as arrangement intent rather than observed attacks. Record user's known
melodic/rhythmic timestamp as a source-bound **USER REPORTED** assertion. It does
not need a detector to agree before being stored, nor become an automatic verdict.

**Next-week35h candidate:** propose reallocation of portions of the existing35h
plan, subject to root/user roadmap reconciliation, using the
canonical allocation in [MILESTONES.md](MILESTONES.md). Produce a controlled
fuller-tone candidate and recorded matched listening choice; legible existing
local UI with source notes; shared capability metadata pilots; corpus/metric
contracts; artifact-ID projection and regression/handoff evidence. This does not silently replace ingestion/click/rhythm milestones or the current
definition of done. Existing functional work may reduce remaining effort, but no
future ticket is already accepted. Full hosted jobs/new frontend/full annotation
rendering are not all included in that budget.
An unsuccessful tone trial remains a useful retained outcome; no guaranteed
recovery of the unknown room sound is promised.

**Optional additional35h:** choose either a small web workflow proof or deeper
local tone/annotation/classification work. These alternatives are mutually
exclusive at70h. Existing XOD/PCEN and other roadmap lanes are substitutions,
not additional hours or repeated research. Full hosting, multiuser scaling,
native-editor import, AU host activation and score/staff transcription are later.

Proposed goal completion requires a demonstrable clip flow, hash-bound immutable
versions, actual changed-input/cancel/replay/refusal evidence, source-bound
annotation readback, visible/suppressed overlay accounting, matched listening
record and reproducible handoff. A staged storyboard is labelled prototype;
only an executed upload/job/download flow counts as web runtime evidence.

## Product and architecture boundaries

Use a typed capability to drive supported agent/function/UI controls: units,
default owner, bounds, dependency requirements, side effects, timeouts and output
provenance. Expose web-safe artifact IDs rather than direct arbitrary file paths.
Not every existing tool is automatically web-admitted; inventory and qualify
individual operations. Offline noise capture/reduction, EQ and compression are
not automatically available in an AU audio callback. Retain realtime-safe gain
state separately from graph/model jobs.

A short architecture decision must compare **SvelteKit control layer + existing
Python/Rust/FFmpeg workers** against **SvelteKit BFF + FastAPI control API** before
committing to two server layers. Rails/Flask are alternatives if justified by the
actual implementation boundary, not mandatory user choices. SQLite/private files
can support a pilot; distributed storage/queues need separate workload evidence.
Investigate xoxd.ai estate patterns and qualify Svelte runes/Effect4/Skeleton5 in
an isolated lockfile fixture. SvelteKit remote functions are experimental; retain
stable form/action/HTTP fallback. [Official remote-function docs](https://svelte.dev/docs/kit/remote-functions)
support that qualification boundary. Framework compatibility is not current app
runtime proof or a mandate to move DSP into JavaScript.

Overlay semantic kind, assertion basis and review state remain independent.
Context includes nullable BPM, tonic/mode/meter, phrase/section/rest and technique;
issues include timing, rhythm pattern, phrase omission/duration, melodic pitch,
articulation, rest execution and meter mismatch. Each automated correctness class
needs its matching reference/evidence; four-click grouping and octave-ambiguous
pitch are insufficient. Default is **Compact: section/phrase label, BPM, and brief
issue badges**; staff/timeline is optional. Source-time precision is distinct
from font/frame/display quantization. Authored SVG or explicitly licensed CC0
assets need attribution/license receipts before adoption; none is downloaded by
this design.

## Proposed SLI/SLO/SLA definitions

An SLI is a recorded ratio/latency with numerator, denominator, clock and named
fixture/host/browser. An SLO is a target evaluated against that measurement.
An SLA is an explicit service/support contract; **none exists here**. Targets
below are unmeasured proposals, not availability/accuracy promises.

| Proposed objective | Measurement and acceptance condition |
| --- | --- |
| Artifact correctness100% | Every published pilot output in20 generated/actual checks has source/upstream/control hashes and native-clock/extent gates; failures produce no successful artifact |
| Tone A/B comparability | Defined common-region loudness difference≤0.3LU; record source, pure denoise, processed/master separately, peak/tail/low-band evidence and operator choice; never infer fan-only SNR or guaranteed32Hz fidelity |
| UI control response p95≤100ms | Named browser/fixture,100 measured interactions; source note/save conflict and actual playback tests at375/390px and200%zoom, no autoplay |
| Metadata p95≤250ms | 1000 bounded successful local metadata requests,10 concurrency, recorded idle host; failures separately counted, excluding upload/hash/probe/render |
| Job accept p95≤500ms | 100 submissions/replays; admission response only, not render completion or upload duration |
| Progress/cancel | 100 committed events visible≤2s;30 owned-fixture cancel trials ack≤500ms/stop≤5s; uncertainty/failure retained |
| Recovery/no duplicate publication | All accepted jobs accounted for and zero duplicate publication in30 declared failure injections; partial qualification states exact exercised subset |
| Overlay coverage100% | Each selected interval maps to visible/suppressed ledger or explicit unsupported status; VFR source mapping and delivery identity checked; readability requires sampled and dense playback tests |
| Classification | No numeric accuracy SLA; full lineage, zero take-family leakage and no unreviewed automatic confirmation are gates. Later report per-class coverage/errors/abstentions only on reviewed heldout labels |

Processing-time percentiles require representative timed jobs/hardware before a
target is chosen. Current slow offline renders cannot become UI job-time promises.
Hosted uptime, retention, support response and incident obligations require a
later host/service owner and operational evidence; reliability prototype tests
alone are not a hosted SLA.

The [future index](README.md) links all independent lane designs. The
[ticket manifest](linear-ready-tickets.json) is ready for root to upsert queued
work, reusing D2/D4/D7/cross-cutting issues where noted. It records dependencies,
acceptance, estimates and exclusive budget choices without due dates. No source
implementation, deployments, model downloads, tracker writes or extra goal/tool
activation occurs in this design lane.


## Later tracker checkpoint — October 6

STAFF and MODEL were created as TIN-5553 and TIN-5554 after service access recovered. All eight new child tickets and four existing scope additions have returned write receipts. Six dependency updates returned; a renewed HTTP 429 leaves STAFF/MODEL relationship writes and full independent readback pending. The complete dependency graph remains in `linear-ready-tickets.json`. See `docs/agent-notes/2026-10-06-future-linear-dependencies.json` for exact IDs. This supersedes only the earlier creation-pending status; activation, budgets and current delivery scope are unchanged.

## Verified tracker closeout — October 6, 04:47 UTC

All eight new queued issues TIN-5547 through TIN-5554, four existing future-scope
appendices, parent TIN-5546, four future milestones and new-child dependency
relations have now been independently read back. Earlier pending states above
are historical. UI and RELEASE retain explicit WEB-only JOBS/STACK dependencies
in their descriptions; these do not block their core local scope. Evidence:
[full readback](../../agent-notes/2026-10-06-future-linear-final-readback.json) and
[conditional dependency readback](../../agent-notes/2026-10-06-future-linear-conditional-readback.json).
No future work was activated or marked complete; budgets remain unchanged.
