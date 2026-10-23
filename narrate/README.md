# narrate

Turn a script into a voiced narration track in a consented voice, check every chunk, and deliver audio, captions,
a narration EDL and a manifest that says the voice is synthetic. The rules are in `../docs/spec/NARRATE.md`; the
types are in `dhall/`; the engine bench lives in `bench/`.

## Quick start

Run these from the repository root.

```sh
nix develop .#condense                       # ffmpeg, whisper-cpp, python3, just, ruff
python3 -I narrate/dhall/check.py --write-fixtures "$NARRATE_STORE"   # the fixture voice's private store
export NARRATE_LEXICAL_DIR=/path/to/xoxd-lexical/dist                 # the pinned release, fetched explicitly
just narrate-render narrate/examples/narrate.toml                     # artifacts/narrate/<run_id>/, verified
just narrate-lint narrate-test               # lint and the synthetic-fixture tests
```

`narrate.toml` names the script, the rendered job, engine, voice, consent and pronunciation JSON
(`dhall-to-json` renders of `dhall/`), the private store and the lexical release. The store and the release live
outside git. `NARRATE_STORE` and `NARRATE_LEXICAL_DIR` override the file.

| Recipe | Command | Does |
| --- | --- | --- |
| `just narrate-render [CONFIG]` | `python -m narrate render` | the whole pipeline, then `verify` |
| `just narrate-eval RUN [CONFIG]` | `python -m narrate evaluate` | loudness, overruns, WER, SIM; writes nothing |
| `just narrate-verify RUN` | `python -m narrate verify` | re-hashes the run and re-checks the manifest |
| `just narrate-voices [CONFIG]` | `python -m narrate voices` | voice ids, consent state, scopes, engines |
| `just narrate-engines [CONFIG]` | `python -m narrate engines` | profiles, confidentiality eligibility, availability |
| `just narrate-voice-add CONFIG CLIP TEXT ID CONSENT` | `python -m narrate voices add` | stores a 10 to 30 s clip and its transcript by sha256 |
| `just narrate-bench` | | lane W3 (TIN-7085) fills it |

## The pipeline

| Module | Step |
| --- | --- |
| `adapters.py` | plain text, markdown manuscript, SRT, WebVTT, condense `words.json` (+ EDL), `SPEAKER:` dialog → script IR (`ir.py`) |
| `policy.py` | consent, scope, revocation, stored clip and transcript digests, hosted and confidential refusals |
| `lexical.py` | the pinned xoxd-lexical release by digest; advisory Pattern findings and Vale; the RewriteCheck |
| `chunker.py`, `normalise.py` | chunks of at most `chunkMaxCodepoints` spoken codepoints; the pronunciation table |
| `engine.py` | `POST /v1/audio/speech` with `ref_audio` and `ref_text`, or the offline fake engine |
| `qa.py` | per-chunk WER through condense's whisper path, SIM placeholder, best of `maxTakes` by seed |
| `audio.py`, `render.py` | pauses, timing fit, placement, two-pass loudnorm, captions, EDL, manifest |
| `verify.py`, `evaluate.py` | the re-check and the scores |

- **Refusals come first.** A missing, revoked or out-of-scope consent, a clip or transcript whose digest no stored
  file has, an unmapped dialog speaker, a hosted engine without `allowHosted`, and any engine that may not run a
  confidential job are refused before any audio exists. The refusal prints `{"refused": code}` and exits 1.
- **Fake engines.** `fake://sine` makes a deterministic tone whose length follows the text and the speed knob.
  `fake://espeak` uses espeak-ng when it is on PATH and records its version, else falls back to the sine.
- **QA.** Without whisper-cli or the model, WER is `not_measured` and no gate judges a take. With them, a take
  over `maxChunkWer` is synthesised again with the next seed; the best take is kept and a chunk that never
  passes is flagged `qa_failed`. SIM is `not_measured` until a speaker-verification model is registered.
- **Timing fit.** A segment over its target first gets the engine's `speed` (at most `[fit] speed_max`, 1.15),
  then `atempo` within the job's `fitMaxStretch` (8%). What still runs over is flagged `overrun` with its excess,
  never truncated. A segment under its target is padded; one whose start has passed starts late, flagged.
- **Loudness.** Two-pass `loudnorm` to the job's target (-16 LUFS, -1.5 dBTP), both passes recorded, then
  measured with `ebur128`; outside the job's tolerance the run is flagged.
- **Captions** are timed from the script placement (`captions.source: script_timing`), in the written text,
  with a synthetic-voice notice when the consent record asks for one. Whisper alignment of the delivered audio
  is a later step.

## Outputs

`artifacts/narrate/<run_id>/` holds `narration.wav` and `narration.flac` (the engine's native rate), the chunk
WAVs under `chunks/`, `narration.srt` and/or `narration.vtt`, `narration.edl.json`, `ir.json` and
`manifest.json`. The manifest's timeline mapping is `narration_v1` with `no_time_stretch: false` on every run,
so no guitar tool and no `video-utils verify-run` path accepts it (`../docs/spec/TIMELINE_CONTRACT.md`). It
records digests and ids only, never a store path: input and IR digests, the lexical pin and findings, the
pronunciation table digest and substitutions, engine record and knobs, each voice's clip, transcript and
consent ids, every chunk's takes, seeds, WER and SIM, the fit per segment, loudness, flags and
`content_sha256`, a digest of everything but the run id, run directory and time, so two renders of the same
inputs compare equal.
