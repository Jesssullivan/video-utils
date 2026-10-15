---
name: condense-transcribe
description: Transcribe talk recordings with whisper.cpp.
---

# Let an agent run the condense transcribe stage on one talk with bounded time and typed failures, and inspect what it wrote.

**Hook (draft):** MCP tool `condense_transcribe` in `program/tool-drafts/condense.json`. Not admitted yet: `tools/list` does not show it until root admission (TIN-6511).

**Capability:** Extract 16 kHz analysis audio and run whisper.cpp twice per ~800 s chunk (a beam pass and a DTW pass) with the registered ggml-small.en model. Reads the clip recordings and the registered model; writes work/<clip>.16k.wav, .pass1.json and .dtw.json beneath the config's work/out paths.

## Use and controls

Fallback recipe: `just condense-transcribe talk.toml`. Run inside `nix develop .#condense`. Every stage reads one talk.toml; `condense/README.md` gives each rule and default.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply, and no guitar tool accepts its outputs (docs/spec/TIMELINE_CONTRACT.md). The 80 Hz high-pass and levelling apply only to the copy whisper reads. Recordings, transcripts and renders stay out of Git.

## Limits

- Synthetic-media tests cover the stage; listening quality, ASR accuracy and physical A/V sync beyond the avsync probe are not established.
- Refuses without the registered, hash-verified model in models/; never downloads it (just condense-model is a separate explicit step).
- DTW word starts can run up to 0.6 s early; pass 1 hears more words with looser times.

## Agent iteration

Read the stage's printed summary and the files it wrote (work/<clip>.16k.wav, .pass1.json and .dtw.json). Change one talk.toml number, rerun this stage and the ones after it, and compare. A finished stage is not an accepted edit: condense_check gates the render and a person reads the bounds report. Never download a model or upload media implicitly.
