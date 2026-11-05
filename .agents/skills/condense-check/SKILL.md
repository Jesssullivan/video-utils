---
name: condense-check
description: Gate a rendered edit.
---

# Let an agent run the condense check stage on one talk with bounded time and typed failures, and inspect what it wrote.

**Hook:** MCP tool `condense_check` (admitted as tool 53, experimental). Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. The worker is `python -m condense check`; the talk.toml path rules in docs/spec/CONDENSE_TOOL_CONTRACT.md are checked before it starts.

**Capability:** Run the named checks (default all): silence (no 1.0 s gap at -35 dB), loud (within 1 LU, true peak under 0 dBTP), sync (probe, real and joined medians within 20 ms; a median needs 4 clear spots, else not_measured) and bounds (whisper re-reads at cuts for a person). Reads the output and edl.json; writes work/check.json when all four gates ran, else work/check.partial.json, beneath the config's work path: status passed, partial, not_measured or failed, each gate's limits, measures and verdict, every tried sync spot, and a summary, bound to the sha256 of the output and edl.json only. It does not measure the captions, the corrected copy or the upload copies. Exit 1 when a gate fails or is not measured.

## Use and controls

Fallback recipe: `just condense-check talk.toml`. Run inside `nix develop .#condense`. Every stage reads one talk.toml; `condense/README.md` gives each rule and default.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply, and no guitar tool accepts its outputs (docs/spec/TIMELINE_CONTRACT.md). The 80 Hz high-pass and levelling apply only to the copy whisper reads. Recordings, transcripts and renders stay out of Git.

## Limits

- Synthetic-media tests cover the stage; listening quality, ASR accuracy and physical A/V sync beyond the avsync probe are not established.
- bounds prints text for a person to read; it does not pass or fail on its own.
- A run of fewer than four gates never replaces work/check.json; condense_publish refuses a newer check.partial.json of the same edit that says failed or not_measured.

## Agent iteration

Read the printed report and work/check.json (or work/check.partial.json): its status, each gate's verdict, and for sync every tried spot with why it was not clear (sound or picture) and any too_few_spots clip or third. Change one talk.toml number, rerun this stage and the ones after it, and compare. A finished stage is not an accepted edit: condense_check gates the render and a person reads the bounds report. Never download a model or upload media implicitly.
