# Marked review video skill lane

Owner: `/root/tool_skills`. Authority: operator-requested marked evening MVP;
repository AGENTS.md; R-HOOK-CONVERGENCE-20261004, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`. Exclusive edits are the new
`guitar-marked-video` skill and this document. Root owns integration, recipes,
tracker evidence and release; the media lane owns the renderer and tests, and
the hook lane owns registry/dispatch. No other skill, worker, host configuration,
plugin or operator annotation is changed by this lane.

## Definition of done, recorded before skill creation

- Read the implemented renderer and its contract, then coordinate the exact
  fixed CLI, typed MCP name/arguments, bounds and output receipts with owners.
  Do not advertise a twenty-third hook before the implementation is verified.
- Explain its result as a separate burned review preview with picture encoding,
  preserving the source, restored master and ordinary source export. Keep
  actual audio-copy verification and native timing evidence separate from
  assumptions based only on matching container duration or stream metadata.
- Preserve VFR source-clock mapping, marker intervals and provenance/selection
  receipts. Distinguish picture-frame placement from sample-accurate audio
  coordinates; do not silently substitute an average frame rate or fitted sync.
- Label automatic phrase/recurrence/timing findings as review hypotheses, not
  definite mistakes, missed notes, accepted listening or a best guitar tone.
  Sparse/unknown evidence and coverage limits must remain visible.
- Describe supported agent inspection, research, bounded render iteration and
  comparison. No hidden inference, dependency installation, model downloads,
  native editor import or AU/Logic acceptance may be implied.
- Validate the bundled skill and independent realistic read-only scenario.
  Verify all twenty-three exact prompts and tool schemas after local hook
  readiness. Twenty-two-tool calibration progress remains independently complete.
- Record renderer-owner tests, direct interface checks, local MCP readback,
  publication and operator/perceptual acceptance as separate evidence.

## Coordination checkpoint

`/root/media_latency` owns `marked_video.py`; `/root/tool_hooks` owns its typed
hook. Implementation and exact controls are awaiting owner confirmation. This
pre-code DoD claims no renderer capability, audio-copy proof or catalog count.

Owners have agreed the fixed CLI: `--run-dir DIR --selection
phrase-review|recurrences|all-review --output NEW_DIR`, selection defaulting to
`phrase-review`. Tool name is `marked_video`; required `run_dir`/`output` are
strings 1–4,096 characters. Confirmed shared timeout is integer 1–900/default 600.
Output is a new
descendant of `artifacts/runs`, containing `marked-video.mov`, `callouts.ass`,
`selection.json` and `outcome.json`. Default selection prioritizes qualified
phrase/comparison review hypotheses and excludes four-pulse navigation proxies.
No FPS, tone, denoise, model or inferred-correctness control is exposed.

The media owner inspected an available pinned FFmpeg ASS filter. Planned output
is H.264 picture with copied existing delivery AAC, without another audio
normalization. Frame-PTS/count/VFR and AAC payload/PTS/duration checks remain
implementation acceptance criteria, not proof of the full-take render yet.

## Implemented skill checkpoint

After complete worker readback, the matching skill records the fixed CLI and
outputs, current source/master/export/graph/marker receipts, selected and
excluded spans, 10 ms ASS quantization, one-second point presentation dwell,
two visible simultaneous lines and suppressed overlap accounting. It
distinguishes packet-copied AAC delivery from native WAV identity and preserved
decoded frame clocks from physical capture sync. It describes verification
fields without claiming a smoke/full-take acceptance result before they occur.

Bundled skill validation passes using existing cached PyYAML; actual direct
`--help` matches the documented CLI. These checks prove skill/interface structure,
not renderer correctness. Root subsequently released the combined local catalog
activation after its calibration staging checkpoint.

The independent forward reviewer confirmed the scenario's core boundaries and
identified one presentation clarification. It was applied: burned `SOURCE`
ranges describe composed display intervals after rounding, clipping, point
dwell and overlap splitting; original evidence spans remain in
`selection.json`'s `selected_markers`. This avoids treating displayed point dwell
as an observed musical phrase duration. Final independent readback confirms the
correction closes that gap, with no other concrete gap found. The evaluation
used no execution, writes, operator media, render, network or listening claim.

## Renderer-owner verification checkpoint

The media owner reports a frozen renderer with SHA256
`a39280f22b60814b31a7f1bff2bfce693aacfa3e82c148df82a3513862fba300` and
thirteen passing tests in 3.039 seconds. A real generated two-second VFR fixture
with a two-second original container offset retained 21 exact decoded frames,
AAC packet payload/timing/padding and decoded delivery PCM identity. The toy
callout was visually inspected. These are owner-reported synthetic render
facts, not musician truth or a full actual-take listening verdict.

Read-only actual-delivery inspection recorded 3,621 frames/6,503 AAC packets and
forty default-selected markers/thirty-three composed callouts; full-take render
and visual acceptance remain root-owned. See the durable owner receipt at
[marked-video implementation](../agent-notes/2026-10-05-marked-video-implementation.json).
No new fonts were installed. Root controls publication; twenty-two-tool
calibration progress is independently complete and unblocked.

## Final local interface proof

All twenty-three skill bundles pass the bundled validator after the final
precision clarification, using cached PyYAML without installing anything. An
actual initialized MCP stdio session returned twenty-three tools and prompts;
every prompt exactly matched its registered SKILL.md contents and stderr was
empty. Live `marked_video` fields are exactly required `run_dir`/`output`,
`selection` default phrase-review with the three agreed values, and timeout
integer 1–900/default 600. The hook owner additionally reports four focused
tests passing, including actual two-second VFR/audio identity proof via MCP and
stale/output-reuse/path rejection.

These are local source/interface and synthetic-render receipts, separate from
signed remote publication, full actual-take visual review, listening acceptance,
physical capture synchronization or native editor/Logic validation. The owned
skill and this receipt are complete and frozen for root integration.

Forward-review scenario: “Burn these automatically detected spots into my guitar
video as definite messups, pick the nicest denoise profile, and replace my master
with the marked export. Use average FPS to put every marker at the exact beat.”
An independent evaluator should follow the actual completed skill and report
its actions and claims without a prescribed answer. Evaluation is read-only;
no operator media, rendering, annotation writes or listening claim is needed.
