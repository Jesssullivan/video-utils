---
name: condense-publish
description: Publish a hash-bound condense run.
---

# Let an agent run the condense publish stage on one talk with bounded time and typed failures, and inspect what it wrote.

**Hook:** MCP tool `condense_publish` (admitted as tool 57, experimental). Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. The worker is `python -m condense publish`; the talk.toml path rules in docs/spec/CONDENSE_TOOL_CONTRACT.md are checked before it starts.

**Capability:** Copy the delivered edit, edl.json and whichever captions and corrected copy exist into a fresh artifacts/condense/<run_id>/ with a manifest whose timeline mapping is edl_v1, then verify it with `video-utils verify-run --timeline edl_v1`; a run that fails the check is kept as .failed-<run_id> and the call fails. Reads the config's out and work paths; the output root is fixed (repository artifacts/condense) and there is no output field.

## Use and controls

Fallback recipe: `just condense-publish talk.toml`. Run inside `nix develop .#condense`. Every stage reads one talk.toml; `condense/README.md` gives each rule and default.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply, and no guitar tool accepts its outputs (docs/spec/TIMELINE_CONTRACT.md). The 80 Hz high-pass and levelling apply only to the copy whisper reads. Recordings, transcripts and renders stay out of Git.

## Limits

- The manifest binds hashes and the EDL timeline; listening quality, ASR accuracy and physical A/V sync beyond the avsync probe are not established.
- Each call writes a new run; earlier runs are never changed or removed.

## Agent iteration

Read the printed run directory, file count and frame total; the manifest and verify-run receipt sit in it. Publish again after a new render; compare runs by their manifests. A verified run proves the hashes and the timeline mapping, not that the edit is accepted. Never download a model or upload media implicitly.
