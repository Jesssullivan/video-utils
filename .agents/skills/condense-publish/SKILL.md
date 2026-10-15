---
name: condense-publish
description: Publish a hash-bound condense run.
---

# Let an agent run the condense publish stage on one talk with bounded time and typed failures, and inspect what it wrote.

**Hook (draft):** MCP tool `condense_publish` in `program/tool-drafts/condense.json`. Not admitted yet: `tools/list` does not show it until root admission (TIN-6511).

**Capability:** Copy the delivered edit, edl.json and captions into a fresh artifacts/condense/<run_id>/ with a manifest whose timeline mapping is edl_v1, then verify it with `video-utils verify-run --timeline edl_v1`. Reads the outputs and edl.json; writes artifacts/condense/<run_id>/ beneath the config's work/out paths.

## Use and controls

No recipe until C11 lands. Run inside `nix develop .#condense`. Every stage reads one talk.toml; `condense/README.md` gives each rule and default.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply, and no guitar tool accepts its outputs (docs/spec/TIMELINE_CONTRACT.md). The 80 Hz high-pass and levelling apply only to the copy whisper reads. Recordings, transcripts and renders stay out of Git.

## Limits

- Synthetic-media tests cover the stage; listening quality, ASR accuracy and physical A/V sync beyond the avsync probe are not established.
- Pending C11 (TIN-6510): admitted only after the publish stage and verify-run --timeline edl_v1 land.

## Agent iteration

Read the stage's printed summary and the files it wrote (artifacts/condense/<run_id>/). Change one talk.toml number, rerun this stage and the ones after it, and compare. A finished stage is not an accepted edit: condense_check gates the render and a person reads the bounds report. Never download a model or upload media implicitly.
