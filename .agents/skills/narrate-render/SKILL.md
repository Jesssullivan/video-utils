---
name: narrate-render
description: Render a narration in a consented voice.
---

# Let an agent voice a short script in a consented voice with bounded time, typed refusals and a manifest it can inspect and score.

**Hook:** MCP tool `narrate_render` (admitted as tool 58, experimental). Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. The worker is `python -m narrate render`; the path rules and argument checks in scripts/tool_api.py run before it starts.

**Capability:** Run `python -m narrate render --json` on one narrate.toml job: input adapter, lexical pass, chunker, pronunciation, engine (best of maxTakes per chunk), per-chunk WER through whisper when present, timing fit, two-pass loudnorm, captions, narration EDL and manifest, then verify. Every consent, scope, revocation, hosted and confidential refusal happens before any audio exists and returns its typed code. Returns the run directory, the manifest path and a summary (chunks, seconds, loudness, QA counts, overruns, overrides, flags). Reads the narrate.toml, its records, the private store and the script (a file, or inline text written to a private temporary file); writes one fresh run under the narrate.toml out directory (default artifacts/narrate/<run_id>/), never under artifacts/runs/.

## Use and controls

Fallback recipe: `just narrate-render narrate.toml` (add `--json` for the same summary). Run inside `nix develop .#condense` (FFmpeg, whisper-cpp). Knobs: `input` or `text` (at most 4000 characters), `input_kind`, `voice`, `engine`, `seed`, `confidential` (true only), `allow_hosted` (false only), `max_chunk_wer`, `min_sim`, `max_takes` (1 to 3), `chunk_max_codepoints` (40 to 1000), `loudness_lufs` (-30 to -10), `fit_max_stretch` (0 to 0.08), `timeout_seconds` (at most 900). Every override is recorded in the manifest's `job.overrides`.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply. Every narration manifest says `synthetic: true` with timeline mapping `narration_v1` and `no_time_stretch: false`, so no guitar tool accepts it (docs/spec/TIMELINE_CONTRACT.md). Voices need a consent record; v0 clones only the operator's own voice. Reference clips, transcripts, consent evidence, rendered narration and the real registry stay outside Git, found by digest; tool results carry ids and digests, never a store path or a clip.

## Limits

- Synthetic-fixture tests and the fake engine cover the path; a real engine render, its WER and SIM gates and listening acceptance are separate states recorded per run.
- Gate values are placeholders until the bench calibrates them (job gates.calibrated false); a run with no flag meets only the source gate, not listening acceptance.
- Render does not score SIM per take in v0, so every run carries sim_not_measured; narrate_evaluate scores the delivered chunks.
- The job's audio format, captions and narration EDL choice come from the job file; MCP overrides cover the voice, engine, seed, gates, chunking, loudness target and fit limit only.

## Agent iteration

Read run_dir, manifest, chunks, seconds, loudness, qa, overruns, overrides and flags; the manifest records every chunk's takes, seeds, WER and the engine, voice and consent ids. docs/spec/NARRATE.md gives the dataflow, consent policy and outputs; narrate/README.md gives every rule and default. Change one knob (seed, max_takes, chunk_max_codepoints, fit_max_stretch or the engine), render again and compare with narrate_evaluate on both runs. A rendered run is not an accepted narration: narrate_evaluate scores it and the operator's blind listening receipt accepts it. Never download a model, start or stop an engine, or send a clip anywhere implicitly.
