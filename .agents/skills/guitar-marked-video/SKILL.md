---
name: guitar-marked-video
description: Render a separate source-timed guitar review video with uncertain phrase and recurrence callouts, copied delivery audio and explicit VFR verification; do not label automatic findings as confirmed mistakes.
---

# Render a marked guitar review preview

**Hook:** MCP tool `marked_video`, prompt `guitar-marked-video`. Inspect `tools/list` for its current availability and schema. This renderer consumes existing verified export and marker evidence. It does not perform new denoising, choose the best tone, infer intent or approve the performance.

## Use and controls

Required `run_dir` and `output` are paths of 1–4,096 characters beneath the repository's `artifacts/runs/`. The run must exist; output must be a new directory. `selection` is `phrase-review` (default), `recurrences` or `all-review`. Shared `timeout_seconds` is integer 1–900, default 600. No profile, BPM, FPS, sync offset, custom label or encoding knob is exposed.

Optional `arrangement_markers` is an exact same-run-relative marker JSON selector, 1–1,024 characters, and requires explicit `selection:"all-review"`. It selects the arrangement marker set for this preview; it does not merge it into canonical markers or create an assessment. Reject traversal/symlink components and stale assessment/reference/current-artifact hashes. Omission keeps the existing marker workflow and selections.

Direct worker: `python3 scripts/marked_video.py --run-dir "<verified-run>" --selection phrase-review --output "<new-directory>"`. Recipe: `just tool-run marked_video '{"run_dir":"<verified-run>","output":"<new-directory>","selection":"phrase-review"}'`. Read [the renderer contract](../../../docs/spec/MARKED_VIDEO_LANE.md).

For an existing verified arrangement marker file, pass `--arrangement-markers "<same-run-relative.json>" --selection all-review` to the direct worker, or the corresponding two typed fields. This is a supported selection within the existing authorized preview workflow, not a new approval stage.

Default selection includes comparison review hypotheses, possible repeated phrases and possible low-register riffs, excluding four-pulse navigation proxies. `recurrences` keeps recurrence/comparison candidates; `all-review` also includes other review markers and explicitly labelled navigation proxies. Broader selection does not establish meter or correctness. Default/recurrence selections are bounded to 128 markers; all-review is bounded to 5,000. Empty selected picture coverage fails rather than implying no issues.

## Inspect evidence and timing

Require current source/master/export, DAG, flags and generic markers. The renderer recomputes marker evidence and validates current upstream hashes, external context and export checks; stale markers need the owning graph/marker workflow, not silent rebinding. Only unconfirmed `needs_review` flags are accepted. No latest pointer or source, master, existing export/report is replaced.

Arrangement mode additionally revalidates its selected assessment and supplied-reference lineage. Preserve `label_basis`, intended versus observed intervals, approximate reference counts, null/ambiguous boundary support and uncertainty in selection receipts. Reference-equivalent duration is not detected clicks, and an intended-boundary callout is not a newly detected phrase. Arrangement labels remain review prompts without confirmed mistake or performance grades; the same source/frame-clock, picture and copied-audio checks apply.

The current arrangement overlay validator accepts only `program/demo-arrangement.json` and an assessment bound to the run's current pure `denoised.wav`. Custom-reference or other canonical-PCM assessments supported by `arrangement_reference` are not yet accepted by this overlay route.

The separate `marked-video.mov` burns restrained `REVIEW - uncertain` callouts into H.264 picture. Existing delivery AAC is packet copied, not renormalized; this is the delivery track, not a claim of bit-identical native WAV encoding. `callouts.ass`, `selection.json` and `outcome.json` record labels, selected/excluded spans, hashes and checks. FFmpeg/ffprobe and its ASS filter must already be available; no implicit installation occurs.

Preserve decoded variable frame timestamps. Map source seconds using recorded original container origin and the preserved export frame clock; do not substitute average FPS or fit a sync correction. Subtitle times are quantized to 10 ms and displayed on available picture frames, not sample-accurate visible events. Out-of-picture spans are excluded. Point markers receive a one-second presentation dwell, not an invented phrase duration. Burned `SOURCE` ranges describe composed presentation intervals, including quantization, picture clipping, point dwell and overlap splitting; original evidence spans remain in `selection.json` under `selected_markers`. At most two simultaneous callouts are visible; suppressed overlap time remains recorded, so the preview is not an exhaustive visible inventory.

Inputs are bounded to 600 seconds/120,000 picture frames, 20 MB per metadata JSON and 64 MB graph metadata. Media subprocesses and output are bounded; the render has a 600-second inner ceiling and shared invocation deadline. Inspect failures and receipts rather than retrying with uncontrolled resources.

## Verify and iterate

Inspect outcome status and verification: decoded frame count/PTS/last extent, AAC payload/timing/priming/padding, decoded delivery PCM hash, rate/channels and unchanged input hashes. Successful rendering alone does not establish these checks. Even passing checks leave physical capture A/V synchronization, visual review, listening, native editor import and Logic acceptance unverified.

Review intervals and visibility before rendering; compare a supported selection in a fresh output and retain the same master/evidence receipts. Research FFmpeg timing/subtitle behavior when a specific discrepancy arises; use actual frame-clock evidence. Nine-string near-32 Hz fundamentals, distortion, legato, rests, tuplets and sweeps make detected attacks and recurrence differences ambiguous. A callout is a listening prompt, not a missed-note or rushed-beat verdict. Follow [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for durable evidence. Profile comparison or definite musical grading belongs to its own authorized tool/reference workflow.
