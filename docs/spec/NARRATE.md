# Narration (`./narrate`)

Authority: operator decisions of 2026-10-22 (narrate parent TIN-7084; this spec
TIN-7086; milestones N0 Narration v0, target 2026-10-25, and N1 Narration v1,
target 2026-11-07), repository AGENTS.md, `docs/spec/sprints/20261022-S5.md`
and R-HOOK-CONVERGENCE-20261004 (R-N11, R-N12, R-N13). This spec is written
before the code that implements it. Where it names a later lane, that lane
owns the code and may refine a detail here in the same PR that implements it.

`narrate/` turns text into a voiced narration track. It reads a script (plain
text, a slide manuscript, captions, a condense transcript or a dialog), applies
the estate's pinned writing rules, normalises it for speech, synthesises it
in a consented voice on a pinned engine, checks every chunk, and delivers an
audio track, captions, a narration EDL and a manifest that says the voice is
synthetic. It is a speech workflow beside the guitar workflow and beside
`./condense`, not a guitar default.

## Operator decisions (2026-10-22)

| Topic | Decision |
| --- | --- |
| Owner | A `narrate/` lane in this repository owns the client, CLI, spec, Dhall types, MCP tools and evaluation. Model serving and MCP exposure live in their owning repositories and are changed there only through fork-first PRs or peer dialog |
| GPU use | Attended windows of 30 min or less on the GPU host, each holding the single GPU lease by compare-and-swap and leaving a receipt (load, synthesise, release). Development runs on the Mac host with MLX. Switch-native serving through the model coordinator waits for N1 |
| Voices | v0 clones only the operator's own voice: a 10 to 30 s clip with a human-verified transcript and a consent record. Clip, transcript and consent evidence are hash-bound and kept outside git |
| Engine order | Local open weights first, then rented GPUs running open weights, then hosted APIs last. Hosted engines refuse any job marked confidential |
| Lexical rules | The pinned xoxd-lexical `slides` register plus a local pronunciation table. A narration register is a later upstream bump (TIN-7097) and does not block N0 |

## Lanes

| Lane | Issue | Owns |
| --- | --- | --- |
| W3 engine bench | TIN-7085 | the bench receipt, explicit hash-bound downloads, the engine pick |
| W4 spec, types, registry | TIN-7086 | this file, `narrate/dhall/`, `program/model-drafts/` (models.json v2 draft and narrate entries), the AGENTS.md section |
| W5 CLI and text pipeline | TIN-7087 | the `narrate/` Python package, `just/narrate.just`, the fake engine, synthetic-fixture tests |
| W6a / W6b serving | TIN-7088, TIN-7089 | the interim attended-window path (N0); the switch-native path (N1) |
| W7a / W7b tools, mux, consumers | TIN-7090, TIN-7091 | `program/tool-drafts/` narrate entries, `.agents/skills/narrate*`, the first real render, consumer adapters |

## Dataflow

```
input adapters -> script IR -> lexical pass -> spoken normalisation -> chunker
  -> engine (/v1/audio/speech + ref_audio/ref_text) -> per-chunk QA -> post -> outputs
```

1. **Input adapters.** Each produces the same script IR, a list of
   `{id, speaker, text, target_start?, target_dur?, directions[]}` with ids
   stable across runs of the same input.
   - Plain text: one segment per paragraph.
   - Markdown manuscript (one file per slide, as slide-deck narration
     pipelines use): front matter `slide` and `target_seconds` are read; only
     text before a `Sources:` line is spoken; a line wholly in `[...]` is a
     direction (pause, emphasis), never spoken.
   - SRT/VTT: each cue becomes a segment with `target_start` and `target_dur`.
   - Condense `words.json`: re-voicing a condensed talk. Word times map through
     the condense EDL to the output clock; the condense run is read, never
     changed.
   - Dialog: lines prefixed `SPEAKER:` map to voice ids through the job's
     `speakers` table. An unmapped speaker is refused.
   - Agent-dispatched text arrives through the `narrate_render` tool as segments.
2. **Lexical pass** (xoxd-lexical; see "Lexical pin contract"). Advisory Vale
   findings are recorded. An agent rewrite is accepted only if the
   RewriteCheck holds.
3. **Spoken normalisation.** The Dhall pronunciation table
   (`Pronunciation.dhall`) expands acronyms, units and symbols the engine
   misreads. It changes how a value is said, never the value. The manifest
   records the table id and digest and every substitution made.
4. **Chunker.** Split at sentence, then paragraph boundaries into chunks of at
   most `chunkMaxCodepoints` (300 by default). A sentence longer than the limit
   splits at a clause boundary, then at whitespace. Voice continuity uses the
   engine's continuation or reference mode on every chunk.
5. **Engine client.** One OpenAI-compatible call per chunk:
   `POST /v1/audio/speech {model, input, voice, response_format, speed,
   instructions}`, extended with `ref_audio` (the reference clip, sent by
   content, resolved from the voice's digest) and `ref_text` (its verified
   transcript). An engine that ignores `ref_text` is recorded as such. The
   seed is recorded per take.
6. **Per-chunk QA.**
   - Round-trip the chunk through whisper.cpp (the `condense` shell's
     registered `small.en` model or a larger registered one) and compute WER
     against the normalised chunk text.
   - Speaker similarity (SIM) between the chunk and the reference clip with a
     registered speaker-verification model.
   - A chunk that fails either gate is regenerated with a new seed, at most
     `maxTakes` takes in all (best-of-3 by default); the best take by WER,
     then SIM, is kept and the failure is recorded. A chunk that still fails is
     flagged in the manifest, never silently accepted. WER is a regression
     gate, not a ranking: rare-word errors are adjudicated by a person.
7. **Post.**
   - Loudness to -16 LUFS integrated, -1.5 dBTP true peak (two-pass FFmpeg
     `loudnorm`), within 0.5 LU.
   - Pauses from directions and the job's sentence and paragraph pause knobs.
   - Timing fit for segments with a target duration: first the engine's
     `speed` knob, then FFmpeg `atempo` within plus or minus 8%
     (`fitMaxStretch`). A segment that still overruns is flagged
     `overrun` with its excess, never truncated and never stretched further.
8. **Outputs** (see "Outputs and where they live").

## Engine profiles

A profile is how a job reaches an engine. Real engine instances carry private
endpoints and live outside git; the repository holds the type and the fake
engine only.

| Profile | Backend(s) | Where | Notes |
| --- | --- | --- | --- |
| `gpu-switch` | `VulkanAudioCpp`, `QwenTtsCpp`, `LlamaTts` | the GPU host through the model coordinator | N1. Switch to the TTS entry, synthesise, release to the prior model. Needs a TTS entry kind, an audio canary and the speech route in the coordinator (TIN-7096) |
| `gpu-direct` | same | the GPU host in an attended window | N0 interim. The server holds the GPU lease for the window (30 min or less) and scales to zero after; the window leaves a receipt |
| `mac-mlx` | `MlxAudio` | the Mac host | Development and fallback. No GPU lease involved |
| `rented-open` | `RentedOpen` | a rented GPU running open weights | Confidential jobs only when the host is estate-controlled and flagged |
| `hosted` | `Hosted` | a third-party API | Last resort, public content only, explicit flag per job |
| `fake` | `Fake` | in process | Deterministic tone per chunk for tests. No GPU, no weights, no network |

**Preference order** when a job names no engine: `gpu-switch` (once N1
lands), `gpu-direct` (only inside an open attended window), `mac-mlx`,
`rented-open`, `hosted`. The CLI never escalates to `rented-open` or `hosted`
on its own: those need the job to name the engine, and `hosted` also needs the
job's `allowHosted` flag. Model candidates and their pins are in
`program/model-drafts/narrate-tts-v2.json` (Ming-3.0-tts-0.5B, the favoured
primary; Qwen3-TTS-12Hz-1.7B-Base, the fallback and baseline; VoxCPM2, the
third arm; Fish Audio Drama 3, the rented tier). W3 picks among them.

## Consent and confidentiality policy

- **No voice without consent.** A job declares its `scope` (`OwnContent` or
  `ClientDisclosed`). Every voice it uses (`voice` and each `speakers` entry)
  must name a consent record whose `evidenceSha256` matches stored evidence,
  whose `scopes` include both the job's `scope` and the voice's `scope`, and
  which is not revoked; the voice's `scope` must equal the job's, and the job's
  `engine` must be in the voice's `allowedEngines`. Otherwise the job is refused
  (`consent_missing`, `consent_revoked`, `consent_scope`). v0 has one real
  voice: the operator's own. A voice's reference clip is 10 to 30 s; the
  synthetic fixture voice is a 10 s sine, so it needs no exemption.
- **Hosted engines** need both the job's `allowHosted` flag and the consent
  record's `hostedAllowed`. A job marked `confidential` is refused on any engine
  for which `Engine.mayRunConfidential` is false
  (`confidential_engine_refused`): every engine that is hosted by any of its
  `hosted` flag, `profile` or `backend`; every engine that is rented by its
  `profile` or `backend` and is not both estate-controlled and flagged
  `confidentialAllowed`; and every engine whose `profile` and `backend` disagree
  (`Engine.consistent`, the "Engine profiles" table). A single wrong field never
  makes an engine look local. The rule is defined once in
  `narrate/dhall/Engine.dhall` and its truth table is asserted in
  `narrate/dhall/policy-test.dhall`. `narrate/dhall/check.py` ports it to
  Python and applies it to the rendered examples; the W5 client implements the
  same rule and tests it against the rendered JSON.
- **Clips never enter git.** Reference clips, transcripts, consent evidence,
  rendered narration and the real voice registry live in a private store
  outside the repository, found by digest. Tracked files carry digests and
  synthetic fixtures only. The repository is public: no voice clip, real
  script under confidentiality, host name or personal path in tracked files,
  CI or logs.
- **Synthetic label.** Every manifest sets `synthetic: true`. When the consent
  record sets `syntheticLabelRequired`, captions and the delivery description
  carry a synthetic-voice notice. Client deliverables need explicit
  disclosure. Licence notices an engine requires (for example "Built with
  Fish Audio" for Drama 3) are carried into the manifest and the delivery
  description.
- **Watermarks** are best effort and recorded as such; codecs and resynthesis
  strip them.

## Lexical pin contract (xoxd-lexical)

A job pins one xoxd-lexical release by all of:

- `release` (for example `xoxd-lexical@0.2.0`) and `commit`;
- `lexiconSha256`: the `dist/estate-lexicon.json` digest the release's
  `DIGESTS` file pins with the tag (tag and digest together);
- `promptDigestSha256`: `dist/prompt-digest.txt`, injected when an agent writes
  or rewrites the script;
- `valeRegister` and `valeRegisterSha256`: the Vale register file (`slides`
  for N0). Vale findings are advisory and recorded, never blocking;
- `rewriteCheck`: when true (the default), a rewrite that changes any spoken
  number, unit or identifier is refused (the XL-ACC RewriteCheck rules).

The pass refuses to run with a digest that does not match the fetched release.
The release is fetched explicitly and hash-bound like a model; nothing is
fetched implicitly.

## Outputs and where they live

Narration runs live under `artifacts/narrate/<run_id>/`, outside
`artifacts/runs/`, like condense. They are never guitar runs.

- Per-chunk WAV at the engine's native rate (recorded), and the final track as
  WAV or FLAC at that rate.
- SRT and/or VTT built from the whisper alignment of the delivered audio.
- A narration EDL per `docs/spec/TIMELINE_CONTRACT.md`. Narration is a **new
  track** laid on an output clock: each segment's start on that clock, its
  duration and any fit stretch applied to the narration audio. Source media is
  never time-stretched.
- **Guitar tools must refuse every narration manifest.** Guitar consumers
  check only `timeline.no_time_stretch is True`, and a render whose segments
  needed no `atempo` fit did no stretching, so that flag alone cannot keep them
  out. Every narration manifest therefore writes `timeline.no_time_stretch:
  false` and a non-identity `timeline.mapping` (never absent, `null` or
  `"identity"`), whatever stretch was applied. The narration mapping value is a
  TIMELINE_CONTRACT amendment W5 proposes with the code, together with a
  narration row in the contract's refusal-matrix test showing each guitar
  consumer and `verify-run` refuse a narration manifest with zero applied
  stretch.
- `manifest.json` with `kind: "narration_render"` and `synthetic: true`,
  recording: input and IR digests; the lexical pin and Vale findings; the
  pronunciation table digest and substitutions; engine id, profile, model,
  Hub revision and file digests, seed and knobs; voice id, reference clip and
  transcript digests and consent id (never a path); per chunk its span,
  transcript, WER, SIM, takes and flags; loudness measured; overruns; licence
  notices and watermark status.
- Consumer adapters may also write `NN-<slide-id>.wav` into a slide-deck
  pipeline's narration folder, so its assembler needs no change.

## MCP tools

Each tool gets a strict `inputSchema` in `program/tool-drafts/` and a skill
under `.agents/skills/` (W7a), admitted in its own PR.

| Tool | Does | Knobs |
| --- | --- | --- |
| `narrate_render` | Render a job; returns the manifest path and a summary | `input` (inline segments or a script file), `input_kind`, `voice`, `engine` (optional; preference order otherwise), `confidential`, `allow_hosted`, `max_chunk_wer`, `min_sim`, `max_takes` (1 to 3), `chunk_max_codepoints`, `loudness_lufs`, `fit_max_stretch` (0 to 0.08), `audio_format`, `captions`, `seed`, `timeout_seconds` (at most 900; longer scripts go through the CLI) |
| `narrate_voices` | List voice ids with consent state, scopes and allowed engines | none; never returns a path or clip |
| `narrate_evaluate` | Score a rendered run or a bench take: WER, SIM, loudness, overruns, optionally UTMOS | `run`, `metrics`, `reference_voice` |
| `narrate_engines` | List engine profiles, availability, lease or switch state and confidentiality eligibility | `profile` filter |

## Evaluation and acceptance states

Source checks, a rendered narration and listening acceptance are separate
states, recorded separately:

1. **Source checks:** `just narrate-dhall-check`, the W5 synthetic-fixture
   tests (timing fit, dialog mapping, `words.json`, overrun flag, consent
   refusal, confidential refusal) and an end-to-end run with the fake engine.
2. **Rendered:** a real render on the picked engine produces audio, captions,
   EDL and manifest; every chunk passes its WER and SIM gates or is flagged;
   loudness is within 0.5 LU of the target.
3. **Listening acceptance:** the operator's blind A/B listening receipt.
   Metrics never stand in for it.

The bench (W3) preregisters a fixed public text of about 800 words and one
consented reference, and measures real-time factor, peak VRAM, WER, SIM and
UTMOS. Gate values in the example job are placeholders (`calibrated: false`)
until the bench sets them. Every scoring model needs its own registry entry.

## Types (`narrate/dhall/`)

`Engine`, `Voice`, `Consent`, `Job` and `Pronunciation`, collected in
`package.dhall`. `dhall-to-json` renders instances; Python reads the JSON.
`examples/` holds the only instances in git: the fake engine, a fixture voice
bound to a generated ten-second sine (`narrate/dhall/check.py` regenerates it
and checks the digest), a fixture consent record, a pronunciation table and a
job. `Engine` binds each weight file by `files : List { path, sha256 }`, as
the registry draft does, and `sampleRateHz` is optional until measured.
`just narrate-dhall-check` type-checks and format-checks every file,
re-renders the examples against the committed JSON, checks the fixture
digests, checks every reference a job depends on (engine, voices, speakers,
pronunciation table, consent, scope, revocation, hosted and confidential
refusals), validates the models.json v2 drafts against the draft schema and
runs `check.py --self-test`, which mutates copies of the inputs and expects
each mutation to be refused; CI runs it in the offline job.

## Registry draft

`program/model-drafts/models-v2.schema.json` drafts schema version 2 of
`program/models.json` for multi-file snapshots: `files[]` with `path`,
`sha256` and `bytes`, plus `backend`, `hf_revision`, `vram_gib`, `licence`
and primary `links`. `program/models.json` is unchanged and
`scripts/model_prefetch.py` does not read the draft. A file's `sha256` stays
`pending` until W3's verified download binds it; byte counts come from the
pinned Hub listings and are not yet measured locally. The bench lane's
`narrate/bench/sources.json` is the source listing: `check.py` requires each
draft snapshot to list the same files (model cards excepted) with the same byte
counts, and a bound `sha256` to equal the Hub-declared digest there. A
conversion whose source revision is stated records it as `upstream.revision`.
Scoring models (speaker verification, quality) have no draft entries yet;
they are listed in `sources.json` and need their own entries before a
registered gate uses them.

## Guitar axioms

The guitar axioms in AGENTS.md (low-end protection, no blanket high-pass,
musical-mistake review) govern guitar takes, not narration speech. Narration
ships no guitar default and no guitar tool reads a narration manifest.
