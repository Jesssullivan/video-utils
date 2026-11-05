---
name: narrate-engines
description: List narration engines and their reachability.
---

# Let an agent see which engines a job may use and which answer, before it spends a render on one.

**Hook:** MCP tool `narrate_engines` (admitted as tool 60, experimental). Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. The worker is `python -m narrate engines`; the path rules and argument checks in scripts/tool_api.py run before it starts.

**Capability:** Run `python -m narrate engines` on one narrate.toml: each engine id with its profile, backend, model, licence and licence notice, whether it is hosted, whether its profile and backend agree, whether it may run a confidential job, and its availability; with probe_reachability, a 2 s TCP connect to each http engine (no request, no token, no synthesis). Never an endpoint. Reads the registry records; writes nothing.

## Use and controls

Fallback recipe: `just narrate-engines narrate.toml` (`python -m narrate engines CONFIG --reach` probes). Knobs: `profile`, `probe_reachability`.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply. Every narration manifest says `synthetic: true` with timeline mapping `narration_v1` and `no_time_stretch: false`, so no guitar tool accepts it (docs/spec/TIMELINE_CONTRACT.md). Voices need a consent record; v0 clones only the operator's own voice. Reference clips, transcripts, consent evidence, rendered narration and the real registry stay outside Git, found by digest; tool results carry ids and digests, never a store path or a clip.

## Limits

- A reachable port is not a working engine: only a render proves the speech route, the model and the reference-clip handling.
- GPU lease and model-switch state are not read here; the attended-window receipt holds them.

## Agent iteration

Read id, profile, backend, hosted, consistent, may_run_confidential, licence_notice, available and reach per engine. docs/spec/NARRATE.md "Engine profiles" gives the preference order and who may run confidential work. Probe again after an engine starts; never start, stop or switch a server from here. An engine is usable for a job only when the render admits it; this listing is advice. Never download a model, start or stop an engine, or send a clip anywhere implicitly.
