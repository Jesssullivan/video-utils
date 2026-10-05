# Editor marker compatibility spike

Plan recorded before adapter research, October 5, 2026. Owner `clip_baseline`;
exclusive files: this specification and `docs/research/EDITOR_MARKERS.md`.
Authority: operator's existing ten-hour goal and
[graph integration lane](GRAPH_INTEGRATION_LANE.md), ending October 6 at
06:49:34 UTC. This adds no new allocation to the approved 35+35-hour week.

## Objective and definition of done

Specify bounded future adapters from verified source-time review markers to
Final Cut Pro XML and DaVinci Resolve marker workflows. Distinguish clip/media
time, edited timeline time, exact sample time, video frame snapping, rational
rates and display timecode. Preserve uncertainty: discovered phrase boundaries,
possible skipped/rushed passages and unknown meter are review hypotheses.

Research primary Apple/Blackmagic documentation and applicable versions; inspect
existing generic JSON/CSV and the actual take's metadata/decoded frame times.
Deliver exact coordinate rules, readable labels, reject/abstain cases, bounded
fixtures and separate source/application acceptance. No adapter implementation,
editor installation/configuration, API writes/imports, recording upload or host
compatibility claim is authorized in this documentation lane.

## Current input facts

Generic markers use `source_time_seconds`, `end_seconds`, `name`, `confidence`,
`status`, and `evidence`; source/upstream hashes are checked. Existing exports
explicitly leave frame indices unresolved and native editor import unsupported.

The recorded manifest identifies the 150.954059 s source with mono 44.1 kHz AAC,
video `avg_frame_rate=108930/4549`, `r_frame_rate=24/1`, and `time_base=1/600`.
Audio/video start values are zero. Video header duration, average-rate metadata,
container duration, and decoded frame coverage are distinct; none is an implicit
conform rule. Read-only decoded-frame inspection found 3,621 frames with varying
24/25/26-tick PTS steps at `1/600` s. Last PTS plus reported frame duration is
150.885 s, leaving approximately 69.059 ms of audio beyond this decoded video
coverage. The [research receipt](../research/EDITOR_MARKERS.md) records exact
counts, hashes and primary sources. Editor interpretation remains unverified.

## Future adapter contract

The next development milestone has three bounded parts: a common coordinate
planner, an FCPXML formatter, and a Resolve source-clip operation planner.
Keep the existing generic exporter unchanged until this contract is implemented
and tested. An executable Resolve writer and application validation are separate
work; this lane implements neither.

Inputs are a provenance-verified marker JSON, its run manifest, a hash-bound
decoded-PTS table, and an explicit editor profile. The profile records target
application/version/build/edition, target media identity, source-clock origin,
clip local origin and in/out, exact host rate, timecode display mode/origin,
selected FCPXML version where applicable, and mapping/calibration evidence.
Paths resolve locally; a selected source hash must match. A selected derivative
requires its own hash and verified source-to-derivative timing map.

Outputs are `marker-plan.json` and an exact-time sidecar. A verified supported
profile additionally permits `review.fcpxmld/Info.fcpxml` or a Resolve operations
JSON. An unresolved profile produces a readable plan with
`native_export_status=calibration_required`, without a writable native payload.
The sidecar includes original marker IDs, original decimal timestamps, available
rational/sample coordinates, derived coordinates, quantization error, collisions,
range restrictions, source/upstream/profile hashes and exporter version.
Maximum input size follows the existing exporter bound of 50,000 flags; the
initial native plan limit is 1,000 resulting host markers. Exceeding it returns a
selection-required result with counts, not a truncated export.

### Coordinate rules

1. Preserve the canonical source clock. If an event is originally expressed as
   sample index `n` at rate `Fs`, its source time is `A + n/Fs`, where `A` is the
   verified decoded-audio origin. Do not add stream start a second time. Existing
   decimal source seconds may be represented as their exact decimal rational;
   this does not recover sample accuracy absent from the original artifact.
2. Let `P0` be the first source presentation origin and `C0` the corresponding
   editor asset-local origin. For an unretimed clip, source time `s` maps to
   local media time `C0 + (s-P0)`. A clip starting at local `I` and placed at
   parent offset `O` has parent timeline time `O + (local-I)`. Display timecode
   origin is recorded independently. Reject retiming, reversal, nested edits
   and rate reinterpretation until a verified explicit mapping exists.
3. Preserve the decoded source PTS table. For video preview, use the frame whose
   presentation interval contains the event, recording its index and PTS. This
   index is not automatically a Resolve frame ID or an FCP project-frame number.
   Gaps, duplicate/nonmonotonic timestamps and unavailable final duration require
   explicit coverage handling. Never infer PTS as `index / avg_frame_rate`.
4. On a verified uniform editor grid with frame period `D`, point coordinates
   round to the nearest frame, with exact half ties toward the later frame.
   Half-open spans `[s,e)` round their start down and end up; duration is at least
   one frame. Record signed point error and both span-boundary errors. At 24 fps,
   nearest-point error is at most `1/48` s; outward expansion is less than one
   frame per boundary. These are repository policies, not claimed host rules.
5. Before native output, every selected point/span must lie in the target clip
   and verified media coverage. Negative source times can be valid when the
   source clock starts negative; they are not blanket invalid. Never clamp an
   out-of-range marker into the first/last frame without recording an explicit
   permitted boundary representation. Audio-only tail flags remain in the
   sidecar and report as `outside_video_coverage` for this video adapter.
6. VFR mapping requires a host profile confirming how that application maps
   presentation time to its marker coordinates. The original take therefore
   remains calibration-required even though its nominal metadata says 24 fps.
   No resampling, speed change, new freeze frame or silence padding is implicit.

### Final Cut Pro profile

Use an event containing a source/browser `asset-clip` for the initial adapter;
do not create or overwrite the user's project. Reuse a host-exported minimal
clip template in the future calibration session so asset format, local origin,
extent and the selected schema reflect the host's interpretation. The published
DTD 1.10 is the initial source fixture profile, not a latest-version claim.
Validate against the exact profile DTD and package `Info.fcpxml` in `.fcpxmld`.
Use local media URLs with correct URL/XML escaping; do not embed/copy the take.

Marker `start` uses asset-clip local time, not time elapsed since the trimmed
clip starts. Marker `duration` is one frame of the verified clip format.
Represent a phrase span with two points: `START · P012 · recurrence difference`
and `END · P012 · recurrence difference`. Notes on both retain `[s,e)`, original
source seconds, confidence/status and the shared marker ID. An end exactly at
clip out cannot occupy the next clip: represent it on the last valid frame only
with an explicit `exclusive_end_at_clip_out` note and sidecar mapping. Otherwise
return a boundary-unrepresentable result. Do not invent visible range-marker
semantics by assigning a multi-second XML duration.

Use ordinary markers initially; no favorite/reject ratings, chapter markers or
automatic `completed=1`. Native marker acceptance cannot establish listening,
mastering or musical-correctness acceptance.

### Resolve profile

Target the explicitly selected original `MediaPoolItem` for source annotations,
not the current timeline or an arbitrary timeline item. First obtain the actual
installed scripting documentation and confirm the marker interface, frame
origin, duration units, accepted numeric types, palette and readback support.
Historical manufacturer training establishes visible range markers; it does not
prove the current Python marker contract. If the documented API supports it,
retain an opaque stable ID in marker custom data; do not rely on its visibility.

The first deliverable is operations JSON with no execution side effects.
Future writes require a selected matching source, a version-bound calibration
profile, previewed operations and existing-marker inspection. Preserve user
markers. Same-frame conflicts return a conflict result; no overwriting or
timestamp shifting. Multiple planned observations at one frame may be combined
into one marker only by an explicit deterministic policy retaining every ID in
the sidecar and notes. Reapplication skips an identical owned marker by verified
identity; a changed owned marker is a reported conflict until a replacement
workflow is explicitly approved. Do not assume external scripting availability
from old free-versus-Studio guidance.

### Readable review annotations

Use short neutral names: `REVIEW · phrase transition · P012` or
`COMPARE · recurrence timing · R004`. Notes state exact original times, candidate
status, confidence, feature coverage, comparison partner, quantization error and
an ID/hash prefix linking the local report. Keep detailed arrays in the sidecar;
do not dump them into a marker title. Preserve Unicode and XML-special text.
Unknown meter, uncertain metronome identity and sparse pitch evidence remain
visible. Avoid labels such as “wrong note,” “missed beat,” or “bad playing” from
unsupervised features alone. Reviewed means a person inspected the annotation;
it does not mean the hypothesized mistake is confirmed.

## Required bounded fixtures

These are proposed tests for the future adapter; they were not implemented or
run by this documentation lane.

| Fixture | Required result |
| --- | --- |
| Source sample 44,100 at 44.1 kHz; verified audio origin 0.125 s | Exact source time 1.125 s; do not add the origin twice. |
| FCP clip `start=5s`, marker local `8s`, parent `offset=10s` | Marker is 3 s into the clip and at parent 13 s, matching Apple's example semantics. |
| Source PTS origin −0.5 s and event −0.2 s; editor local origin zero | Local event 0.3 s is valid; raw negative time alone does not reject it. |
| Point at `1/48` s on a 24 fps editor grid | Tie maps to frame 1; error `+1/48` s is recorded. |
| Span `[1.01,1.02)` at 24 fps | Outward grid bounds 24 and 25; one-frame Resolve range, paired one-frame FCP points with original short span retained. |
| Point at 1 s with parent timeline display origin one hour | Source/local identity unchanged; displayed timecode includes the independent origin. |
| 29.97 DF boundary | Labels `00:00:59;29` → `00:01:00;02`; media frame count remains consecutive. Ten-minute boundary does not skip `;00`/`;01`. |
| 24 fps NDF versus exact `24000/1001` NDF | Preserve distinct rational periods; neither is inferred from this clip's average rate. Initial DF support is limited to calibrated `30000/1001`. |
| Variable PTS `[0,25,49,75]/600` | Use the actual PTS table; native frame IDs stay unresolved without a host mapping. |
| Real take at 150.90 s | Keep exact audio time; flag outside measured decoded video coverage ending 150.885 s. Do not create a video marker silently. |
| Real take's final decoded PTS `90506/600` | Source preview selects final frame; native assignment requires host-calibrated tail behavior. |
| Span ending exactly at clip out | Explicit last-frame FCP boundary representation, or an abstention; no marker on the following clip. |
| Duplicate same-frame observations; preexisting user marker | Preserve IDs; deterministic explicit combination or conflict; no overwrite/shift. |
| Unicode label with `&`, `<`, quotes and line breaks | Safe native serialization and unchanged canonical text after readback. |
| Stale source/upstream hash, escaping/symlinked input, invalid span, unbounded count | Reject before producing native operations; never change source files. |
| Retimed, reverse, mixed-rate, nested or mismatched selected clip | Abstain until its explicit timing mapping is supported and verified. |
| Repeat a calibrated import | No duplicate owned markers; unchanged user markers; changed plans are conflicts. |

For the actual take, the proposed 24 fps span `[150.86,150.954059)` would produce
outward bounds 3620 and 3623 on a hypothetical uniform grid. That arithmetic is
not a valid import mapping: it crosses the measured video tail and requires
application calibration. This fixture should exercise abstention.

## Acceptance and week allocation

Source acceptance requires meaningful coordinate/serialization fixtures, exact
provenance and sidecar round-trip, valid selected-version XML, dry-run conflict
handling and a real-take plan that honestly abstains when mapping is missing.
Use the existing day-six annotation/report work and day-seven handoff allocation;
these tasks replace part of that scope rather than adding hours to the 35-hour
baseline. If host access/calibration is unavailable, deliver the generic markers
and source-only planner and retain the native-adapter milestone as pending.

Application acceptance is separate: record exact version/build/edition, use a
disposable user-selected review event/clip, inspect first/middle/last markers,
trimmed and nonzero-origin fixtures, and the audio/video tail. Resolve requires
API readback plus visual comparison; Final Cut requires re-export comparison
plus visible point/span-pair inspection. Check that the source is unchanged,
audio timing is not conformed, and user markers remain intact. No app installation,
configuration, import or SDK write is performed in this lane.

## Completion receipt

`clip_baseline | two assigned documentation files and read-only source inspection
| native marker design needs exact editor coordinate semantics | existing operator
goal; R-HOOK-CONVERGENCE-20261004 R-N12/R-N13 | generic export supported; native
import unverified | source-only research and bounded design complete; native
implementation and application acceptance pending`

Research used primary Apple documentation, manufacturer Resolve publications
and a read-only delegated Resolve research lane. Decimal/rational fixture
arithmetic was checked in memory. Only these assigned documentation files were
written; current exporter, media, application state and sibling repositories
were unchanged by this lane.
