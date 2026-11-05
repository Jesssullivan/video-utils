---
name: narrate-evaluate
description: Score a narration run.
---

# Give agents measured, typed evidence on a narration run (and its decoy) before anyone listens.

**Hook:** MCP tool `narrate_evaluate` (admitted as tool 61, experimental). Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. The worker is `python -m narrate evaluate`; the path rules and argument checks in scripts/tool_api.py run before it starts.

**Capability:** Run `python -m narrate evaluate` on one run directory after re-verifying it: loudness (EBU R128 against the job target), overruns (from the EDL), WER (each chunk cut from narration.wav and read back by the registered whisper model) and SIM (each chunk against the speaking voice's reference clip with the registered ECAPA speaker-verification model on the CPU, plus wSIM, the minimum over 10 s windows). A metric whose model or runtime is missing is not_measured with its reason, never a number. reference_voice scores every chunk against another voice's clip (a decoy check). Reads the run, the narrate.toml and the private store; writes nothing.

## Use and controls

Fallback recipe: `just narrate-eval RUN narrate.toml`. Knobs: `metrics` (loudness, overruns, wer, sim), `reference_voice` (a decoy or cross-voice reference). SIM needs `just narrate-sim-model` once and an interpreter with torch and speechbrain named in `[sim] python` or `NARRATE_SIM_PYTHON` (for example the `python3` of `nix develop .#ml`); with neither set, SIM is not_measured and no torch starts. The SIM worker uses 1 to 8 CPU threads (`[sim] threads`, default 4).

**Host:** SIM is torch inference on the CPU. On Linux this tool starts an evaluation that asks for wer or sim inside `systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 nice -n 19 ionice -c3`, and refuses those metrics where that scope cannot be made. `narrate evaluate` holds the host's one-scorer lock, shared with the bench scorer: while another scorer runs, wer and sim are not_measured, never queued. Check `/proc/pressure/memory` first; the Mac build host also works. No TTS model runs on the shared CPU host, and the tests use a fake worker. Every reference voice (the speaking voices, or reference_voice) passes the consent check first: a revoked or out-of-scope consent gives not_measured with `refused`.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply. Every narration manifest says `synthetic: true` with timeline mapping `narration_v1` and `no_time_stretch: false`, so no guitar tool accepts it (docs/spec/TIMELINE_CONTRACT.md). Voices need a consent record; v0 clones only the operator's own voice. Reference clips, transcripts, consent evidence, rendered narration and the real registry stay outside Git, found by digest; tool results carry ids and digests, never a store path or a clip.

## Limits

- SIM is the cosine of ECAPA embeddings trained on VoxCeleb; the microphone and room move it as well as the voice, so a cross-channel reference scores lower. Its gate is uncalibrated until the bench sets it against a decoy.
- SIM needs the registered model (just narrate-sim-model) and an interpreter with torch and speechbrain named explicitly ([sim] python or NARRATE_SIM_PYTHON; there is no default); otherwise it is not_measured. On the shared CPU host it runs one scorer at a time inside a 6G memory scope; no TTS model runs there.
- WER is a regression gate, not a ranking; rare words are adjudicated by a person. UTMOS is not scored yet.
- Metrics never stand in for the operator's blind listening receipt.

## Agent iteration

Read each metric's status; for sim read median, min, wsim.min, the per-chunk rows (short marks a chunk under 1 s), min_sim and calibrated; for wer the per-chunk rows and passed. docs/agent-notes/2026-10-22-narrate-bench-plan.md defines the SIM bar against a preset-voice decoy and wSIM; narrate/sim.py says what a SIM number means. Score the same run with reference_voice set to a decoy voice and compare medians; score two renders of one script to compare engines or seeds. Measured scores are evidence for a gate, not acceptance; the operator's blind A/B listening receipt is a separate state. Never download a model, start or stop an engine, or send a clip anywhere implicitly.
