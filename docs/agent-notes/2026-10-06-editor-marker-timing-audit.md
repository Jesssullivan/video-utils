# Independent editor-marker timing audit

Actor: `media_latency`. Authority: root's reattached independent audit assignment,
operator's active ten-hour parallel goal, R-HOOK-CONVERGENCE-20261004 and R-N13.
Owner `resolve_marker_sources` implements the planner. This lane owns this dated
audit and a new meaningful regression only if source review reveals a gap.

Plan before review: wait for the owner's source freeze, inspect the pure planner
and existing tests, exercise nonzero/negative source and clip origins, exact
24 versus 24000/1001 grids, point ties, outward half-open range quantization,
same-frame conflicts and VFR membership. Verify bounded hash-bound selection,
all retained hidden flags, truthful unknowns and always-unverified native import.
Do not rerender, re-probe all media, invoke an editor, or edit owner files.

Definition of done: report source hash and actual test evidence, distinguish
source-coordinate planning from hypothetical host frame IDs, and record any
material defect with a reproducer. Native import compatibility, application
readback, physical capture synchronization and musical correctness remain
unverified. Source validity or XML schema conformance cannot substitute for them.

Pre-review evidence: the existing actual preview audit proves 3,621 decoded VFR
frames and last extent 150.885 seconds. Full-clock SHA256 is
`94cb5ba5067bb8bce27a62a15202629f1db70dc09dac65b49a79df9bb5ea0e70`.
The full timestamp array was not persisted: only three exact samples and this
digest/count/extent are retained in `marked-preview/visual-proof/audit.json`.
A digest and three samples do not establish a source frame map. The owner was
informed to retain nullable native membership/calibration-required status unless
a complete explicitly source-bound PTS table already exists; no average-rate or
partial-sample interpolation is acceptable. Root requested no repeated full
probe absent changes.

Native planning must use original source spans from current generic markers.
The ending selected recurrence has an original end beyond picture extent;
the rendered ASS interval was clipped and quantized to 149.66–150.88 seconds.
It cannot replace that source span. All 24 selected observations, including six
entirely suppressed video callouts, and all 156 exclusions must remain traceable.

Status at creation: source implementation pending; no planner test or native
import claim made yet. The published video and its current inputs are untouched.

Independent expected arithmetic, checked with standard-library `Fraction` before
reading the implementation: source origin −1/2 and event −1/5 map to asset-local
3/10; with clip in 1/5 and parent placement 10, parent position is 101/10.
At 24 fps, exact point 1/48 ties toward frame 1. Span [101/100,51/50) expands to
host grid bounds 24 and 25, with signed errors −1/100 and 13/600 seconds.
For VFR PTS [0,25,49,75]/600, event 2/25 seconds is in preview frame index 1
at PTS 1/24; a hypothetical nearest 24 fps grid instead produces index 2.
The two indices must remain separate evidence. These are expected fixture
calculations, not a planner pass or host compatibility result.

Completed independent audit: worker SHA256
`738e6cd3ee84b0c41ec93bb19987c1b2b7f5ab59e06eea4fedadda5bac4b8e3d`;
owner test SHA256
`87fed25463a7d8261de3fe415319e5dd3b908ce5f6aa76a3bce131f675dfe825`.
The combined command `python3 -m unittest discover -s tests -p
'test_editor_marker*.py' -v` passed all 21 tests in 0.061 seconds: 16 owner
tests and five independent regressions in
`tests/test_editor_marker_timing_audit.py` (SHA256
`e6f0afd97a9e31e7be5c3e292bde82eb02ae10fc2b503bf1a605ff3290e3544f`).

The audit found a real boundary defect in the original reviewed worker
`4bcf7f85f77791d1a217028ebe9ef93909056f8fd06e329287ef0b1a8ec3c892`:
source coverage was checked before fixture rounding, while rounded positions
were checked only against clip bounds. With VFR starts [0,25,49,75]/600 and
durations [25,24,26,25]/600, the source point 33/200 is inside the last frame.
The nearest 24 fps position is frame 4, at 1/6, exactly the exclusive video end.
A descriptive action could therefore address picture coverage that did not
exist. No native action was enabled.

The owner corrected coverage after rounding using the inverse map
`source = source_origin + asset_position - asset_origin`. Resolve point
fixtures require their complete one-frame interval; ranges require the complete
outward-rounded interval. FCP paired markers require continuous coverage through
the END point's one-frame interval, and remain atomic on failure. Clip-out END
boundary abstention retains its separate reason. A failed picture check now
records `fixture_quantization_outside_video_coverage`, retains source spans and
signed rounding errors, and emits no action. The five new regressions cover the
exclusive final frame, nonzero/negative origins, an atomic FCP pair, rounding
into a VFR gap, and a fully covered descriptive point.

The owner's final decimal-lexeme change also passed review: JSON time
`0.100000000000000001` becomes the exact rational
`100000000000000001/1000000000000000000`; marker IDs retain compatibility with
the current generic-marker serializer. Frame membership, hypothetical fixture
grid positions and parent timeline positions remain separate. Conflicts report
existing or same-frame annotations without shifting or merging them.

A read-only pure plan from the published actual `markers.json` and
`marked-preview/selection.json`, with explicit source/asset origins zero and
clip-out 150.885 seconds, retained all 180 markers as 24 selected and 156
excluded. It retained the six entirely suppressed video selections. Without a
complete source PTS table or host calibration, all preview/native frame IDs were
null, all actions were empty, and status was `calibration_required`. Twenty-three
rows recorded `video_coverage_unverified`; the ending range recorded
`outside_clip` and preserved its source end `1207689/8000` (150.961125 seconds).
This is metadata coordinate evidence, not a new media decode or graph run.

Audit acceptance is limited to the pure source planner and fixture timing tests.
It produces stdout JSON, not an import file, and every action and plan remains
`executable: false` / `native_contract_unverified`. No editor was invoked, no
actual media was probed or rendered, and no source, run receipt, render or latest
pointer changed. Parent retains CLI publication and future typed-hook admission.
