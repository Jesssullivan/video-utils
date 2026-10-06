# Source-timed overlays and operator annotations

Status: future design, October 6, 2026. Existing behavior is distinguished below
from proposed behavior. Authority: operator's requested future UI/tooling lanes;
R-HOOK-CONVERGENCE-20261004 and R-N13. This specification adds no server, renderer,
asset dependency or publication. Current evidence is in
[the dated inventory](../../agent-notes/2026-10-06-overlay-annotation-inventory.md).

## What exists

The canonical NR8 run is `artifacts/runs/20261005T232741Z-2b5dc43fd009`.
Its 180 generic markers contain eight kinds; the default preview selects six
kinds and 24 markers, excludes 156, and composes 25 callouts. Six selected markers
have no visible time because overlap priority suppresses them. These are review
hypotheses and navigation, not 180 mistakes. Counts are specific to this frozen
run, not a constant tool capacity or a complete taxonomy of possible outputs.

| Kind | All markers | Default selected | Video label |
| --- | ---: | ---: | --- |
| `four_pulse_group_review_candidate` | 112 | 0 | Four-pulse navigation proxy |
| `spectral_texture_region_candidate` | 44 | 0 | Texture boundary candidate |
| `automatic_recurrence_review_candidate` | 8 | 8 | Possible repeated phrase |
| `low_register_riff_or_breakdown_candidate` | 3 | 3 | Possible low-register riff |
| `recurrence_attack_density_difference_review` | 4 | 4 | Attack pattern differs |
| `recurrence_relative_rate_difference_review` | 3 | 3 | Loop rate differs |
| `recurrence_relative_alignment_shift_review` | 1 | 1 | Loop alignment differs |
| `recurrence_motif_timing_difference_review` | 5 | 5 | Riff timing differs |

The renderer burns ASS text over picture, limits simultaneous callouts to two,
retains selection/visibility metadata, copies delivery AAC, and verifies decoded
picture PTS and decoded audio identity. Generic JSON/CSV uses source seconds;
frame indices remain null. `all-review` can select navigation/texture markers;
fallback text for an unmapped kind is merely “Review candidate.” Other DAG kinds
exist, including unresolved tempo, recurrence duration differences and approved
reference transient candidates. They are absent from this NR8 inventory and do
not thereby gain a dedicated graphical design.

The local browser review screen has a candidate list, timeline span buttons,
kind/confidence filters, seek, original/clean/residual/video audition, and saved
annotation read/edit/download. Its five categories are
`rhythm|phrase|tone|noise|other`; its three states are
`needs_review|accepted_observation|dismissed_candidate`. It displays declared
and fitted pulse BPM with alternate pulse interpretations. It has no current
structured melodic mistake class, tonic/meter overlay, editable staff, or
user-annotation-to-burned-video route. `accepted_observation` preserves a human
listening observation; it does not certify a mistake or accept a master.

The current worktree also contains a separate arrangement-marker branch:
`arrangement_intended_unit`, `arrangement_aligned_unit_review`, and
`arrangement_boundary_review`. These distinguish intended timing windows from
audio boundary assignments. Their implementation is being validated by the
owning clip lane; no completed actual arrangement render is asserted here.
The supplied 24 phrases/404 clicks are intended layout, not detected counts.

## One annotation model for musician, agent and renderer

Keep three independent fields: **semantic kind**, **assertion basis**, and
**review state**. Confidence is additional detector evidence, never an automatic
transition to a confirmed assertion. A musician may say “known rhythmic issue at
47.25 seconds”; the agent preserves those words and creates an operator assertion
without pretending the detector confirmed it. An imprecise report keeps an
uncertainty interval and never acquires a fabricated exact boundary.
The classifier may additionally carry orthogonal arrangement/phrase identity,
technique and coverage axes. Group issue classes into rhythm, phrase extent,
melodic and articulation families; capture/tone/noise observations retain their
own family without being labelled performance errors.

Proposed context kinds: `section_span`, `phrase_span`, `pulse`, `tempo`, `meter`,
`tonal_context`, `technique`, `rest_span`. Context is not an error class. Phrase
identity and technique carry their own basis; a predicted section labelled
“tapping” from arrangement intent is not observed technique recognition.

Proposed issue classes:

| Kind | Use | Evidence required for an automatic musical verdict |
| --- | --- | --- |
| `rhythm_timing` | Early/late/drifting timing | Approved expected rhythm, pulse interpretation and latency calibration |
| `rhythm_pattern` | Rhythmic pattern differs | Expected pattern plus bounded matched-event coverage; attack counts alone are insufficient |
| `phrase_omission` | Intended phrase reportedly omitted | Approved arrangement and observed coverage through the expected region |
| `phrase_duration` | Phrase/breakdown shortened or extended | Intended duration plus independently observed boundaries; retain tempo/phase uncertainty |
| `melodic_pitch` | Reported wrong/missed/extra pitch | Intended notes, fixed tuning, qualified pitch evidence and ambiguity handling |
| `articulation` | Intended mute/tap/sweep/legato differs | Intended articulation and qualified audio evidence; texture alone is insufficient |
| `rest_execution` | Intended rest interrupted/shortened | Expected rest and music/noise/click separation evidence |
| `meter_mismatch` | Performed grouping conflicts with intended meter | Approved notation/downbeats; four-click navigation or accent-cycle ranking is insufficient |

For absent expected attacks, retain the existing detector wording (“expected
attack not detected”) under an observation; do not map it directly to a missed
note. A tonal hypothesis does not prove melodic correctness. Null tonic, meter,
mode or BPM stays null and can be displayed as “unknown.” BPM retains whether
it is operator-declared, fitted mechanical-click pulse or an alternate half/double
interpretation. Meter retains numerator/denominator only when notation is supplied
or qualified, separately from inferred accent cycles and downbeats.

Proposed assertion bases: `operator_context`, `operator_assertion`,
`detector_hypothesis`, `reference_comparison`. Proposed review states:
`needs_review`, `accepted_observation`, `dismissed_candidate` (compatible with the
current model). A confirmed operator report additionally records
`operator_certainty: confirmed`; labels say **USER REPORTED**, rather than
**DETECTOR CONFIRMED**. Qualification of an automatic musical verdict is a later
evidence state with explicit reference/calibration, not a confidence threshold.

## Agent timestamp dispatch: current route

Read `review` with `run_dir` and `operation: "read"`, then write one local request
file using the returned revision. The existing request schema is closed:

```json
{
  "expected_revision": 0,
  "annotation": {
    "source_start_seconds": 47.25,
    "source_end_seconds": 47.25,
    "category": "rhythm",
    "status": "accepted_observation",
    "note": "Operator reports a known rhythmic issue at source 47.25 s. Exact affected phrase and error subtype have not been supplied."
  }
}
```

The revision and timestamp above are examples, not an annotation made on the demo.
Invoke `review` with `operation: "write"` and `input` pointing to that request,
then read back the stored record. The tool binds source identity through the run
manifest and validates timeline bounds. `candidate_id` is optional: operator
timestamps need no detected candidate. Never invent a candidate ID. For a known
melodic issue use current category `other` and preserve “melodic” in the note until
the versioned taxonomy is implemented. MCP annotation calls do not start a server.
Current HTTP and CLI writes use the same revision-checked atomic storage.

## Proposed typed annotation v2

This payload is a design target and is rejected by the current v1 worker.
Implement an explicit versioned adapter; do not silently add v2 fields to v1.

```json
{
  "schema_version": 2,
  "expected_revision": 3,
  "idempotency_key": "annotation-request-0001",
  "source_sha256": "<64 lowercase hex from the selected source>",
  "manifest_sha256": "<64 lowercase hex from the selected run>",
  "annotation": {
    "kind": "melodic_pitch",
    "basis": "operator_assertion",
    "operator_certainty": "confirmed",
    "status": "accepted_observation",
    "source_span": {
      "start_seconds": 47.25,
      "end_seconds": 47.25,
      "coordinate": "original_source_stream",
      "uncertainty_seconds": null
    },
    "candidate_ids": [],
    "phrase_id": null,
    "detector_confidence": null,
    "raw_detector_score": null,
    "confidence_calibration_sha256": null,
    "reference_sha256": null,
    "source_frames": null,
    "reported_by": {"actor": "operator", "via": "agent"},
    "operator_quote": "Known melodic issue at 47.25 seconds.",
    "note": "Exact intended and played pitches were not specified."
  }
}
```

Tool/UI transport uses the same closed discriminated schema. Context kinds have
typed value objects (e.g. BPM with pulse multiplier, meter with notation basis,
tonal context with nullable tonic/mode), and issue kinds allow only supported
subtypes. Operator certainty and nullable detector confidence are independent.
Uncalibrated scores live in `raw_detector_score` with score definition/producer;
probability-like confidence remains null until its calibration is qualified.
Preserve literal user wording, source/manifest/analyzed-input hashes, upstream
artifact hashes, reference hash when applicable, recorder actor/via, tool version,
UTC creation/update times, and original/updated receipts. Server generates a stable
ID; edits require the ID and current revision. Idempotency keys prevent duplicate
writes after uncertain transport completion; changing content under the same key
is a conflict. Re-reading/reconciliation precedes a stale-revision retry.

Accept finite ordered point/spans inside verified source bounds, including legal
negative source origins. Zero-length observations remain points. For a timestamp
with unspecified extent, preserve `extent_known: false`; an optional future
nullable end normalizes to a point for the v1 adapter, without inventing duration.
Bind optional
`source_frames` to decoded frame PTS table hash, source start, and frame indices
or uncertainty/coverage intervals. Frame numbers are never obtained by multiplying
source seconds by average FPS. Retain out-of-picture audio-tail annotations and
record their exclusion from video. Reanalysis preserves human records by source
identity while candidate links become explicitly historical/stale; it does not
rewrite assertions or force regenerated candidates to match them.

## Graphical design and collision policy

Operator-selected default, verbatim: **“Compact: section/phrase label, BPM, and
brief issue badges.”** Detailed timeline/staff belongs in the review UI or an
explicitly selected optional output. Meter/tonal context is available in the
inspector or optional overlay, rather than filling the default shareable clip.

Use a thin phrase/section ribbon with current phrase ID and progress, a small
context badge for BPM/meter/tonal context, and at most two issue callouts. Labels
include basis: **INTENT**, **REVIEW**, or **USER REPORTED**. Detailed evidence stays
in the interactive inspector and a portable annotation sidecar. Hide unavailable
context by default; an expanded inspector shows “unknown” and why. Reference
phrase clocks remain a range when the approximate anchor or breakdown execution
is uncertain. Never stretch the audio or snap detected boundaries to satisfy the
404-click intention.

Pair symbols and text with color: bracket for phrase span, clock for timing,
waveform for pattern, gap bracket for omission/rest, note outline for melodic
pitch, hand/stroke for articulation, and grouped pulses for meter. Suggested
neutral context, amber REVIEW, and cyan USER REPORTED require measured contrast
against an opaque/dark backing. Meaning must survive grayscale, red/green color
deficiency and icon failure. W3C guidance supports text/shape in addition to color
and a 4.5:1 target for ordinary text. See
[use of color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html) and
[contrast minimum](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).

Reserve a user-selectable safe region away from picking/fretting hands. Keep text
short, allow a 390px layout with readable inspector, and avoid flashing. Use stable
priority: explicit user selection, operator-reported issues, other selected
issues, then context. Do not erase lower-priority records; show `+N more` in the
interactive view and make every omitted/suppressed span downloadable. Video
priority, safe area, maximum concurrent lines and dwell are recorded render knobs
with bounds. A minimum readability dwell changes presentation only; exact evidence
time remains unchanged. Clipping, 10ms ASS quantization, frame availability,
collision suppression and dwell must have separate ledger entries. Acceptance
includes continuous playback of brief/dense sections, beyond still-image checks.

Staff/tab is a later optional view, requiring a supplied score or qualified note
events with tuning, octave/string ambiguity, voicing coverage and clock provenance.
Do not invent notation from arrangement phrases, chroma, sparse Basic Pitch
events or a dominant spectral peak. Until then, waveform/spectrogram and a pulse
lane can display uncertainty without asserting notes. A reference score may show
intended notes while detected notes remain an explicitly separate nullable layer.

## Assets

Prefer repository-authored minimal SVG primitives for the music-specific symbols;
record their author, source revision and project licensing with the files. New
artwork is not automatically CC0. If the owner chooses CC0 dedication, include
that explicit statement and the CC0 text alongside the assets.

Optional general controls: the creator's
[Kenney Game Icons page](https://kenney.nl/assets/game-icons) lists 105 files and
Creative Commons CC0, verified October 6, 2026. The
[CC0 deed](https://creativecommons.org/publicdomain/zero/1.0/) describes copying,
modification and distribution without permission. This verification covers the
creator's published license declaration; no archive/file audit or dependency
adoption has occurred. Before vendoring, verify the downloaded archive's license,
retain exact asset filenames/hashes and attribution/provenance manifest. These
generic controls do not establish a music-specific visual vocabulary. No external
asset network request is required during playback or rendering.

## Milestones, acceptance and property testing

Now: preserve the current inventory and use v1 revision-checked timestamp notes.
Next week: 8–14 engineering hours shared with the UI/backend lanes, estimated:

| Ticket-ready slice | Estimate | Done when |
| --- | ---: | --- |
| Versioned annotations and shared typed schema | 3–5h | v1 adapter retained; eight issue classes; provenance and nullable context; atomic conflict/idempotency tests; typed agent/UI call and readback demo |
| Explicit annotation selection and graphical coverage | 3–5h | new output only; displayed basis; every visible/hidden/excluded interval accounted for; original source clock and copied audio qualified |
| Review flow and visual validation | 2–4h | capture timestamp → agent save → seek/edit → render selection → sidecar/download walkthrough; desktop and390px legibility; dense-section playback receipt |

Later: staff/tab with qualified notes, calibrated automatic issue verdicts,
native editor adapters and verified host import. No frontend framework is selected
by this overlay specification; backend orchestration consumes portable typed data.

Property suite should generate nonzero/negative origins, tempo changes,
half/double interpretations, missing/extra/ambiguous boundaries, partial phrase
coverage, uncertain breakdown length, VFR gaps, points, audio tails, Unicode,
ASS/HTML-like labels, overlapping spans and concurrent revisions. Assert:

1. Translation of the source origin translates observations/presentation mapping
   equally; source-relative relationships stay unchanged.
2. Reference uncertainty remains an interval; detected boundaries can stay
   unmatched, multiple or absent. No test forces the observed 404-click total.
3. Operator context/assertion, detector hypothesis and review state survive
   serialization/CSV-sidecar round-trip without strengthening claims.
4. Missing transient/pitch evidence cannot become a confirmed missed-note label;
   unknown tonic/meter and uncalibrated timing remain unknown/uncalibrated.
5. Candidate/source/input/reference hash changes reject stale selections;
   human observations remain attributable and candidate links historical.
6. Every selected presentation interval equals visible plus suppressed coverage
   within the documented quantization tolerance; zero-picture/audio-tail points
   have explicit exclusions. Deterministic collision order is input-order invariant.
7. Two edits at one revision produce one success and one conflict, with no lost
   update. Identical idempotent retry returns the same record; altered retry fails.
8. VFR mapping uses recorded PTS and never invents missing picture coverage;
   future render qualification verifies frame PTS/count/extent and AAC/PCM identity.
9. Escaping and bounded text cannot inject ASS overrides, HTML or scripts;
   schema, store, renderer and resource bounds reject excess without partial writes.

Synthetic properties establish transport/timing/claim invariants. Actual demo
validation separately measures observed boundaries against operator assertions,
coverage and playback legibility. Musical accuracy, listening acceptance, physical
capture sync, native editor import and AU/Logic acceptance remain separate gates.
