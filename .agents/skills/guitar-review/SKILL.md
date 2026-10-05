---
name: guitar-review
description: Read or save local source-bound guitar listening annotations with revision checks; distinguish accepted observations from confirmed musical mistakes or master acceptance.
---

# Preserve human listening observations

**Hook:** MCP tool `review` and MCP prompt `guitar-review`; inspect `tools/list` for publication status and the current schema. The bounded annotation worker is implemented. MCP annotation calls never start an HTTP server.

## Use and controls

Use `review` with `run_dir` and `operation` (`read` default, or `write`). A write also needs `input`, an existing local JSON request file. Recipe fallback after registry publication: `just tool-run review '{"run_dir":"<run-dir>","operation":"read"}'`. Direct workers: `python3 scripts/review_server.py annotations "<run-dir>"` and `python3 scripts/review_server.py annotate "<run-dir>" --input "<request.json>"`.

Read [the listening review contract](../../../docs/spec/REVIEW_LANE.md). Read the current annotation revision before writing. The request contains `expected_revision` and one `annotation` with finite ordered `source_start_seconds`/`source_end_seconds`, `category` (`rhythm|phrase|tone|noise|other`), `status` (`needs_review|accepted_observation|dismissed_candidate`) and a meaningful 1–4000-character `note`. Include an existing annotation `id` only when updating that record; optional `candidate_id` must identify current verified candidate evidence, never an invented identifier. Source spans use the original source timeline, including stream offsets.

The worker atomically stores `review-annotations.json` with original source identity, revision, stable IDs, UTC timestamps and manifest/candidate receipts. Requests are limited to 20 kB, the store to 1 MB and 200 annotations. Source mismatch and stale revision are errors: reread and reconcile the operator's intended edit rather than blindly resubmitting or overwriting another observation.

## Interpretation and acceptance

Preserve automatic proposals alongside human observations. Unknown phrase intent, meter, tonic/mode or latency does not prevent saving a structural observation. Recurrence differences, triplets, rests, legato and sweeps may be intentional; a nine-string near-32 Hz component can be wanted sustain rather than noise.

`accepted_observation` records a listening observation. It does not accept the master, establish a missed/extra/wrong note, replace detector measurements or claim native editor/AU/Logic behavior. Record what the operator actually heard and the relevant evidence; do not manufacture listening or auto-approve an intended reference. Maintain uncertainty in the note when the recording cannot establish a fact.

The separate local browser review UI can audition media and navigate candidates when explicitly launched through its own entrypoint. Annotation hooks only read/save records; do not launch an enduring server as a side effect.

**Review scenario:** Two edits based on the same revision must not silently overwrite each other. A note saying a shortened recurring phrase deserves inspection can be saved without a score; it remains an observation rather than a confirmed musician error.

## Agent iteration

Inspect the run and current source/annotation receipts, understand the intended observation, propose the smallest record change, save with the current revision and read it back. Research source-time or annotation behavior in the actual worker/contract when uncertain. Record changes and limitations in `docs/agent-notes/`; keep media and annotation artifacts local and ignored. Use [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for shared discovery and evidence handling.
