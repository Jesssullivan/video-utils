---
name: narrate-voices
description: List consented narration voices.
---

# Let an agent pick a voice it may use before a render, from consent state rather than from files.

**Hook:** MCP tool `narrate_voices` (admitted as tool 59, experimental). Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. The worker is `python -m narrate voices`; the path rules and argument checks in scripts/tool_api.py run before it starts.

**Capability:** Run `python -m narrate voices` on one narrate.toml: each voice id with its consent id and state (active, revoked, missing or evidence_absent), scopes, allowed engines, whether hosted use is allowed, whether it is a fixture, and whether its reference clip and transcript are in the private store. Never a path, a clip, a transcript or a digest. Reads the registry records and hashes the private store; writes nothing.

## Use and controls

Fallback recipe: `just narrate-voices narrate.toml`. No knobs beyond the narrate.toml.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply. Every narration manifest says `synthetic: true` with timeline mapping `narration_v1` and `no_time_stretch: false`, so no guitar tool accepts it (docs/spec/TIMELINE_CONTRACT.md). Voices need a consent record; v0 clones only the operator's own voice. Reference clips, transcripts, consent evidence, rendered narration and the real registry stay outside Git, found by digest; tool results carry ids and digests, never a store path or a clip.

## Limits

- The listing reflects the private registry and store as they are; consent evidence itself is checked by digest only, never read or judged here.

## Agent iteration

Read id, consent_state, scope, consent_scopes, allowed_engines, hosted_allowed, fixture, ref_clip_stored and ref_text_stored per voice. docs/spec/NARRATE.md "Consent and confidentiality policy". There are no knobs; a voice that is not active needs the operator, never a workaround. Only an active voice whose clip and transcript are stored can render; v0 clones only the operator's own voice. Never download a model, start or stop an engine, or send a clip anywhere implicitly.
