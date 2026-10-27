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
| Lexical rules | Pinned xoxd-lexical 0.7.0 `narration` register and its shared pronunciation table, followed by the local Dhall overlay (TIN-7097/E7) |

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
3. **Spoken normalisation.** First, each recognised numeric range and dollar
   amount is said in words (see "Ranges and money"). Then the Dhall
   pronunciation table (`Pronunciation.dhall`) expands acronyms, units and
   symbols the engine misreads. It changes how a value is said, never the
   value. The manifest records the table id and digest, every substitution
   made and every range or amount expansion.
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
     against the written chunk text and against its spoken projection, keeping
     the lower. Before the written comparison, each pronunciation entry's spoken
     words in the transcript are mapped back to its written form, so "MCP" and
     "M C P" are both a correct reading of `MCP`. Each comparison also runs
     with any range or dollar amount the transcript wrote in digits said in
     words, so "$5 to $10" and "five to ten dollars" are both a correct reading
     of `$5–$10`.
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

### Voice tempo (2026-10-26)

Operator ruling 2026-10-26: a persona voice may speak faster than its engine,
approved at 1.1. `Voice.dhall` carries `tempo : Optional Double` (0.5 to 2.0;
`None` is 1.0). Between steps 5 and 6, every take passes through one
pitch-preserving FFmpeg `atempo` at the voice's factor, at its own sample rate
(`narrate/tempo.py`, `audio.time_stretch`). QA scores that take, and step 7's
timing fit works on top of it, so its `fitMaxStretch` stays the fit's own. A
tempo of 1.0 leaves the take untouched. A value out of range is refused before
any audio (`voice_tempo_invalid`). The manifest records `tempo` and
`pre_tempo_seconds` per take and `tempo` per voice. Each EDL segment records
`voice_tempo`. The segment's `stretch_applied` still means the fit alone, so a
voice at 1.1 with no fit has `stretch_applied: false` on faster audio.
`Voice.Type` is an exact record: a registry voice written as a plain record
literal must add `tempo = None Double` (or a value) before it re-renders, and
one written as `Voice::{ ... }` takes the default.

## Engine profiles

A profile is how a job reaches an engine. Real engine instances carry private
endpoints and live outside git; the repository holds the type and the fake
engine only.

| Profile | Backend(s) | Where | Notes |
| --- | --- | --- | --- |
| `gpu-switch` | `VulkanAudioCpp`, `QwenTtsCpp`, `LlamaTts` | the GPU host through the model coordinator | N1. Switch to the TTS entry, synthesise, release to the prior model. Needs a TTS entry kind, an audio canary and the speech route in the coordinator (TIN-7096) |
| `gpu-direct` | same, and `AudioCppBatch` | the GPU host in an attended window | N0 interim. The server holds the GPU lease for the window (30 min or less) and scales to zero after; the window leaves a receipt. `AudioCppBatch` is a request batch run in the window, not a server (see "Out-of-process batch engines") |
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

## Host placement and memory

Operator rule after narration work drove the CPU host, a cluster
control-plane member, to NotReady on 2026-10-23 (TIN-7085). It binds every
narrate lane, recipe and test:

- **No TTS model on the CPU host.** No TTS server, no MLX, torch or GGML
  inference and no Vulkan or lavapipe model smoke test runs there. Synthesis
  runs only on the Mac build host (MLX, within its cache and free-space caps)
  or on the GPU host inside its leased window. Tests use fake engines and fake
  binaries.
- **Scorers one at a time, bounded.** Whisper, a SIM model or any other heavy
  scoring step runs one at a time inside a transient user scope with
  `MemoryMax=6G`, at nice 19 and the idle I/O class, whisper with at most 4
  threads, and starts only when memory pressure (`/proc/pressure/memory`,
  `full avg10`) is 10 or below.

Enforcement in the code:

- `narrate/bounded.sh` takes a per-user lock (`flock` on
  `$XDG_RUNTIME_DIR/narrate-heavy.lock`) so a second bounded step on the host
  waits for the first (exit 75 after `NARRATE_LOCK_WAIT_S`; without `flock`,
  as on macOS, it says the step is not serialised). It then waits before
  starting while `full avg10` is above 10 (exit 75 after
  `NARRATE_PSI_WAIT_S`) and runs its command at nice 19 with `ionice -c3`,
  inside `systemd-run --user --scope -p MemoryMax=6G` when a user systemd
  answers. Pressure is read before the start only; during the run the scope's
  ceiling is the bound. Without a user systemd (macOS, a CI container) it says
  so and runs without a ceiling. A nested call is recognised by the outer
  step's pid among its own pid and ancestors, never by an inherited flag, so a
  leaked variable cannot drop the bounds. `just narrate-render` and
  `just narrate-eval`, the recipes that run whisper, go through it.
- `qa.Whisper` caps whisper at 4 threads whatever `narrate.toml` asks.
- `narrate/serve/qwentts.sh` builds and serves only on a host whose machine id
  (`/etc/machine-id`, or `IOPlatformUUID` on macOS) is in the user's private
  allow file `~/.config/narrate/tts-host`, which must be the user's own and
  writable by no one else. No environment variable opens it and no host name
  is in git. `serve` takes `Vulkan0..9` or `MTL0..9` only (`CPU` is a build
  target), hashes the weights against the pin, refuses a build that is not
  current or whose `tts-server` differs from the sha256 in its stamp, never
  builds, and runs the server through `bounded.sh --no-lock` with a 14G
  ceiling. `build` runs both cmake steps through `bounded.sh` with an 8G
  ceiling, in a build tree of the user's own with mode 0700, with git hooks
  off and the origin held to the pinned URL; build before a window opens.

## qwentts.cpp engine (2026-10-23)

qwentts.cpp's `tts-server` at the pin in `narrate/bench/sources.json` does not
read `ref_audio` or `ref_text` on `/v1/audio/speech`. It clones from a voice
registered by name (`POST /v1/audio/voices {name, ref_text, wav_b64}`; ICL
when `ref_text` is present), keeps the registry in memory only, refuses an
unknown voice with HTTP 400 and parses `speed` without applying it. For a
`QwenTtsCpp` engine a render opens one voice session: the first take of each
voice registers the reference under a name made of the voice id, a digest of
clip and transcript and a random per-session nonce, and the session's end
deletes every name it registered (`DELETE /v1/audio/voices/{name}`), on
success and on failure. The client never reads the server's voice list, so an
entry another client registered is never spoken with or recorded as the
operator's clone. A 400 on a later take (a restarted server) registers again
and asks once more. Takes speak by that name with the seed, send no `speed`,
record `speed_honoured: false` and fit timing with `atempo` alone (step 7's
speed knob is skipped).

The pinned server answers every origin with `Access-Control-Allow-Origin: *`.
`narrate/serve/qwentts-loopback.patch` removes that and refuses, before
routing, any request with an `Origin` header (a browser page) or a `Host`
header that does not name the loopback interface (DNS rebinding). Any local
process on the serving host can still reach the loopback port; the nonce names
and the deletion keep a registered clone's exposure to the render that made
it.

`NARRATE_QWENTTS_DEVICE` (`Vulkan0` or `MTL0`) selects the build. A narrate
engine record for it uses `GpuDirect` on the GPU host; `MacMlx` admits
`MlxAudio` only, so a Mac build serves development checks, not a record.

## Out-of-process batch engines (2026-10-26)

The operator picked VoxCPM2 as the N0 engine after the blind A/B of
2026-10-26 (TIN-7085 comment 6767db24). It runs through audio.cpp's `audiocpp_cli` at the pin
`47c2756e`, which has no server: one process loads the model (about 30 s),
renders every request of a `--request-sequence` file and writes one WAV per
request id (48 kHz). A render cannot call it chunk by chunk. The backend
`AudioCppBatch` (profile `GpuDirect` only) renders in three phases, so one
GPU window renders a whole job, every chunk and every retake, with one model
load per voice:

| Phase | Host | Command | Writes |
| --- | --- | --- | --- |
| A | CPU host | `narrate plan CONFIG --out DIR [--takes N]` | `plan.json`, `requests/<voice>.json`, `refs/<sha256>.wav` |
| B | GPU host, in the window | `narrate/serve/audiocpp_batch.py run DIR --requests requests/<voice>.json ...` | `wav/<id>.wav`, `receipts/<voice>.json`, `logs/<voice>.log` |
| C | CPU host | `narrate render CONFIG --prerendered DIR` | the run, as for any engine |

- **Plan.** `plan` runs the render's text pipeline unchanged: the input
  adapter (SRT and WebVTT included), the RewriteCheck, policy, the lexical
  pass, the chunker and spoken normalisation with ranges and amounts. For each
  chunk it writes one request per take the job may keep (`--takes`, 1 to
  `maxTakes`, default `maxTakes`; seeds `seed`, `seed + 1`, ...). It refuses
  everything a render refuses, before any request exists, and also a reference
  the family's encoder cannot take: VoxCPM2's AudioVAE encoder takes 240000
  samples at 16 kHz after padding to a multiple of 2560, so a reference is 5
  to 14.88 s (`ref_clip_misfit`; register a cut from
  `narrate/bench/ref_cut.py`). The plan copies each reference clip from the
  store as `refs/<sha256>.wav`; the directory stays private, outside git.
- **Request id.** A request is `{id, text, seed, voice_ref, audio?,
  reference_text?}`. Its id is the first 32 hex digits of the sha256 of its
  canonical JSON without the id. A WAV named by an id answers exactly that
  text, seed and reference; batches of many runs merge without collisions;
  identical requests are rendered once.
- **Clone.** `[engine] audiocpp_clone = "ultimate"` (the default, the
  operator's choice) sends the reference as `voice_ref` and as `audio`, the
  continuation prompt, with its verified transcript plus one space as
  `reference_text` (the pin joins prompt and target text with no separator).
  `"reference"` sends `voice_ref` alone.
- **Batch.** `audiocpp_batch.py` (standard library, Python 3.9) checks every
  request's id against its content and every reference against the sha256 in
  its name, hashes the binary and the weights against the given pins, runs
  one `audiocpp_cli --task clon --family voxcpm2 --backend vulkan --device N
  --out-format pcm16 --metrics` in its own process group, and stops it at its
  deadline, on a signal, or after `--stall-s` seconds (default 120) in which
  neither its log nor its output directory grew. The pin prints
  `[TIMING] request.<id>.wall_ms` before it writes a WAV and
  `audio_out=<path>` and `metrics[<id>].*` after it, so after a stop a WAV
  counts only when one of the later lines names it. Any WAV counts only when
  it is complete: its RIFF size, chunk sizes and data chunk account for every
  byte, so a take cut short under a full-length header is dropped. The
  receipt lists each output's sha256 and each missing id; the pin prints no
  model load time. `--only-missing` finishes a stopped batch in a later window.
  The runner sets no limit itself: the caller runs it in the window's bounded
  unit (memory, CPU, nice, idle I/O, runtime, VRAM watch, RADV ICD only), as
  for the bench.
- **Render.** `--prerendered DIR` trusts a receipt only when its requests file
  has the sha256 it names, every request carries its content's id, the
  weights' sha256 is the record's `files` entry named like the receipt's
  `model_file` and the binary's another `files` entry, family and task match
  the record's `audiocpp://<family>` endpoint, and each WAV has the sha256
  the receipt lists and is complete (`prerendered_batch_mismatch`,
  `prerendered_engine_mismatch`, `prerendered_take_mismatch`). Before any
  audio is made, a chunk with no take among its `maxTakes` seeds is refused
  (`prerendered_take_missing`), and every take the render may read is checked;
  a script, seed or reference that changed after the plan therefore finds no
  take. Each take is read once and the bytes read are the bytes hashed. QA
  scores every prerendered take a chunk has and keeps the best (passing
  first, then lowest WER, then highest SIM, then the earliest), not the first
  that passes; with nothing measured it keeps the first. A seed the batch
  lacks is skipped and listed in `missing_seeds`; a chunk with no passing take
  keeps its best take and is flagged `qa_failed`, never passed. Timing fit
  (atempo alone: the batch ran before the fit), loudness, captions, EDL and
  verify run as for any engine. `[engine] ref_audio = "omit"` is refused: a
  batch request always names the reference.
- **Manifest.** `engine.synthesis` records `mode: out_of_process_batch`, the
  runtime, family, clone mode, audio.cpp commit, binary and weights sha256,
  and each batch used (receipt and requests sha256, request and output
  counts, exit code, stop rule). Every take records its request id. A receipt
  written in test mode adds the flag `prerendered_test_mode`.
- **Direct calls.** `engine.synthesize` refuses an `AudioCppBatch` record
  (`engine_out_of_process`); a render without `--prerendered` is refused
  (`prerendered_required`), and `plan` or `--prerendered` with any other
  backend is refused (`engine_not_batch`). The MCP tools do not expose `plan`
  or `--prerendered` yet; they stay CLI only until W7 admits them.

An engine record for VoxCPM2 (values are placeholders; the real record is
private):

```json
{"id": "voxcpm2-batch", "profile": "GpuDirect", "backend": "AudioCppBatch",
 "endpoint": "audiocpp://voxcpm2", "model": "voxcpm2-bf16",
 "files": [{"path": "audiocpp_cli", "sha256": "<binary sha256>"},
           {"path": "voxcpm2-bf16.gguf", "sha256": "<weights sha256>"}],
 "sampleRateHz": 48000, "hosted": false, "estateControlled": true,
 "confidentialAllowed": true}
```

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
- **Persona label.** A consent record may name a `persona` (NV-1, TIN-7476
  comment `9db389dc`). A narrated video whose segment uses that voice must
  carry the same `labels.persona` (docs/spec/NARRATED_VIDEO.md).
- **Watermarks** are best effort and recorded as such; codecs and resynthesis
  strip them.

## Lexical pin contract (xoxd-lexical)

A job pins one xoxd-lexical release by all of:

- `release` (for example `xoxd-lexical@0.7.0`) and `commit`;
- `lexiconSha256`: the `dist/estate-lexicon.json` digest the release's
  `DIGESTS` file pins with the tag (tag and digest together);
- `promptDigestSha256`: `dist/prompt-digest-narration.txt` for `narration`
  (legacy registers retain `dist/prompt-digest.txt`), injected when an agent
  writes or rewrites the script;
- `valeRegister` and `valeRegisterSha256`: the Vale register file (`narration`
  for the 0.3.0 and later consumers). Vale findings are advisory and recorded, never blocking;
- `rewriteCheck`: when true (the default), a rewrite that changes any spoken
  number, unit or identifier is refused (the XL-ACC RewriteCheck rules).

The digest-verified `estate-lexicon.json` also authenticates the shared
pronunciation table. Narration refuses a missing or malformed table. Its entries
run in longest-written-form order before the explicit local Dhall table. The
local table is an overlay: a local entry whose written form matches an upstream
entry's, ignoring case, replaces that upstream entry, and the manifest lists
each replaced upstream entry in `pronunciation.upstream.overridden_by_local`.
Both layers keep separate digest/substitution evidence. Written-script RewriteCheck
runs before either spoken projection. Both layers keep the digit-run guard and a
quantity guard: each substitution must keep every numeric literal's sign and
notation and every recognised unit, allowing only the explicit spoken aliases
(`-16` and `minus 16`, `8%` and `8 percent`). The recognised units are one
table, `lexical.UNITS`, which the RewriteCheck and the chunker also protect. The
guard is a bounded regex check, not a proof of semantic equivalence; entries
still need review. The pinned 47-entry table passes the text-only consumer
qualification.
The guard never lets a table entry turn `3-5` into `3 to 5`; ranges are said
by the next section's stage, which checks its own output by value.

### Ranges and money

`narrate/amounts.py` runs before both pronunciation layers. It is engine
agnostic: every engine receives the same words. The written script, the
chunks' written text and the captions keep their digits.

| Written | Spoken |
| --- | --- |
| `$12,400–$27,000` | twelve thousand four hundred to twenty-seven thousand dollars |
| `17–19 Oak Lane` | seventeen to nineteen Oak Lane |
| `120–275 h` | one hundred twenty to two hundred seventy-five hours |
| `$2,346.08` | two thousand three hundred forty-six dollars and eight cents |
| `$700` | seven hundred dollars |
| `$4.75–$9.20` | four dollars and seventy-five cents to nine dollars and twenty cents |
| `5-12%`, `$5-$10` | five to twelve percent, five to ten dollars |
| `$600 through $850` | six hundred through eight hundred fifty dollars |

- A range is two unsigned amounts in ascending order joined by an en dash
  (no spaces, or one space on each side), by `to` or `through`, or by a
  hyphen-minus with no spaces. A hyphen-minus, `to` or `through` range needs
  a `$` or a recognised unit to mark it: `314-422` and `3 to 5` stay as
  written. `B`, `x` and `dB` do not mark a hyphen-minus range (`Apt 3-4 B`,
  `rooms 2-4 x 8`, `10-5 dB`). A money range joined by `to` or `through`
  needs a `$` on both sides.
- A unit after the second amount comes from `lexical.UNITS` and is said by its
  plural spoken alias; a unit after the first amount must be the same unit.
  `B` is never a range's unit, `x` only against the digits (`2–3x`), and a
  bare `s` written against the digits is not taken as a unit (`1990–2000s`).
- Left as written: signed amounts (`-$5`, `-5–10 dB`); amounts next to a
  letter, digit, underscore, slash, dot, comma, colon, `#`, `@`, `§`, a
  currency sign other than a leading `$`, a sign or another dash (`x86-64`,
  `A7_31/0/88`, `2026-10-26`, `9:00–10:30`, `1–2–3`, `€5–10`, `TIN-7087`);
  money with a scale word or suffix (`$2 million`, `$5k`, `$5-year`); cents
  not in two digits (`$1.5`); leading zeros (`01–05`); descending or equal
  ranges (`10–5`); an em dash or a spaced hyphen-minus (`5—10`, `5 - 10`);
  and a range with no `$` or unit whose integer part has four or more
  ungrouped digits: years, phone numbers and standards (`1990–1995`,
  `555–1234`, `ISO 9001–2015`). `1,200–1,450`, `$1000–$2000` and
  `1000–2000 h` are still said.
- A pronunciation entry with a digit in its written form is the opt-out: the
  stage leaves any span such an entry matches, in either layer, as written
  for the entry to say (`17–19` -> `17 through 19`). The digit and quantity
  guard still checks that entry.
- Each expansion is read back: an independent parser turns the spoken words
  into values, unit and connector, and any difference from the written digits
  refuses the render (`NormaliseError`). Grouping commas are not part of the
  value; every other digit is (`1.50 s` is said "one point five zero").
- The pronunciation tables never see an expansion's words. Each expansion is
  held out of the text while both layers run and put back afterwards, so a
  table entry cannot change a value or unit after the read-back (`fifteen` ->
  `sixteen` and `dollars` -> `euros` do not reach an expansion), and the
  manifest's spoken form is what the engine receives.
- The manifest's `pronunciation.expansions` lists each expansion per segment
  with its kind, written and spoken forms, connector, values with units and
  count. WER maps a spoken expansion in the transcript back to its written
  form, as it does a table entry.
- The chunker never splits inside a written range or amount, as it never
  splits a protected span.
- The RewriteCheck accepts a rewrite that says a recognised range or amount in
  words when the words read back to the original's values and form a whole
  number phrase: no sign word or sign before them, and no number, `and` with
  a number, scale word, `hundred`, `point`, cents, currency or unit after
  them. `seventeen to nineteen` keeps `17–19`; `eighteen to nineteen`,
  `seventeen to nineteen hundred`, `minus five dollars` for `$5`, or `$12400`
  for `$12,400`, is refused. A number the recogniser does not take (`3 to 5`)
  must keep its digits.

This is a bounded recogniser, not a general number parser. Only dollars are
said; other currencies stay as written for the engine.

The private lexical release stays outside this public repository. No table or
Vale style is vendored into public source, and no implicit fetch is added.

The pass refuses to run with a digest that does not match the fetched release.
The release is fetched explicitly and hash-bound like a model; nothing is
fetched implicitly.

### Checking only the voiced text (TIN-7097)

`xoxd-lexical check --register narration` on a raw manuscript page also
checks lines no render voices. On one field script, 977 of 983 findings were
on front matter, `[at m:ss: ...]` and `[clip: ...]` lines, `<!-- -->`
comments and `Sources:` lines (TIN-7097 comment 723dd1b6).
`python -m narrate spoken INPUT` runs the input through the render's adapter
and prints only the IR's segment text, the written text the lexical pass
reads. `lines` puts each voiced paragraph on its own line with a blank line
between them. `json` gives `[{id, text}]` per segment, with `start_s`,
`dur_s`, `speaker` and `origin` when the input has them. `srt` needs cue
times and refuses an untimed input. `just narrate-lexical-check INPUT` pipes
`lines` into the check CLI. It uses the release a render reads
(`NARRATE_LEXICAL_DIR`, else `lexical` in `narrate.toml`), linked as `dist/`
in a temporary `XOXD_LEXICAL_HOME`, and the `bin/xoxd-lexical` beside it or on
PATH. It refuses a CLI whose `version` differs from that release's. It does
not verify the job's digests. A render still does. Without the CLI or Vale,
or with another release, it says so and exits 0 (R-N12). Otherwise it exits as
the CLI does: 1 for an Error-severity finding, 2 for a fault. The MCP tool
drafts are unchanged.

## Outputs and where they live

Narration runs live under `artifacts/narrate/<run_id>/`, outside
`artifacts/runs/`, like condense. They are never guitar runs.

- Per-chunk WAV at the engine's native rate (recorded), and the final track as
  WAV or FLAC at that rate.
- SRT and/or VTT on the output clock (v0: script timing; whisper alignment of the delivered audio later).
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

`narrate plan` and `narrate render --prerendered` (the `AudioCppBatch`
phases) have no tool yet; W7 owns their admission.

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
`package.dhall`. The narrated-video types `Edition`, `MusicBed` and
`NarratedVideo` sit beside them (docs/spec/NARRATED_VIDEO.md, TIN-7476).
`Consent` carries an optional `persona` (NV-1): the AI-persona name that a
persona voice's manifests carry as metadata (KP-15), `None` by default, with the real value in the private
record. A narrate render does not read it. `dhall-to-json` renders instances; Python reads the JSON.
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
Scoring models are listed in `sources.json`; each needs its own registry
entry before a gate uses it. The speaker-verification model (speechbrain
ECAPA, `embedding_model.ckpt`) is registered in `program/models.json` by W7a;
the quality model (UTMOSv2) has no entry yet.

## W5 implementation choices (2026-10-23)

Lane W5 (TIN-7087) refines these details with the code in `narrate/` (see `narrate/README.md`):

| Topic | Choice |
| --- | --- |
| Narration mapping | `timeline.mapping: "narration_v1"`, `no_time_stretch: false` on every run; the TIMELINE_CONTRACT amendment and its refusal-matrix row land in the same PR |
| Private store | Clips, transcripts and consent evidence are found by hashing the files of the store directory (`NARRATE_STORE`); a file whose digest differs is not found, so a changed clip refuses as `ref_clip_missing` |
| Markdown | One segment per slide file; headings, HTML comments and inline markup are not spoken; `[pause]`, `[pause 2s]` and `[pause 800ms]` add silence, other directions are recorded only |
| Chunking | Chunks are cut on the written text and checked on the spoken text; a chunk whose spoken form runs past the limit is packed again word by word |
| Timing fit | The speed knob goes up to `[fit] speed_max` (1.15) before `atempo` |
| Captions | v0 times cues from the script placement (`captions.source: script_timing`); whisper alignment of the delivered audio is a later step |
| Audio | Every run carries both `narration.wav` and `narration.flac`; the job's `audio` names the one consumers take first |
| Narration EDL | Always written, whatever the job's `narrationEdl`: `verify` and the timeline contract read it |
| `ref_audio` | Sent as a base64 WAV data URI (`[engine] ref_audio = "omit"` sends neither field); whether a server reads that form is checked per engine in W6 |
| Vale | Run only when `vale` is on PATH; otherwise recorded `not_run` |
| Exit codes | A refusal prints `{"refused": code}` on stderr and exits 1; a flagged run (overrun, `qa_failed`, loudness, `wer_not_measured`, `sim_not_measured`, `input_unpinned`) still publishes and lists its flags; only a run with no flag meets the acceptance gate |

## W7a implementation choices (2026-10-23)

Lane W7a (TIN-7090, tools half) refines these details with the tools:

| Topic | Choice |
| --- | --- |
| Admission | `narrate_render`, `narrate_voices`, `narrate_engines`, `narrate_evaluate` are tools 58-61 (`program/tool-drafts/narrate.json`, `tests/test_s5_tool_admission.py`); each runs `python -m narrate COMMAND` from the checkout with a process-group deadline |
| Render input | `input` (a file) or `text` (at most 4000 characters, written to a private temporary file of the job's input kind); `timeout_seconds` at most 900 |
| Render knobs | voice, engine, seed, `max_chunk_wer`, `min_sim`, `max_takes`, `chunk_max_codepoints`, `loudness_lufs`, `fit_max_stretch`; `confidential` only as true and `allow_hosted` only as false, so MCP never loosens a job. Audio format, captions and EDL stay in the job file. Overrides are recorded in `job.overrides` |
| Voices | ids, consent state, scopes, allowed engines, hosted permission, fixture and stored flags; never a path, clip, transcript or digest |
| Engines | the registry view plus an opt-in TCP connect (2 s, no request, no token); never an endpoint. Lease and switch state are not read |
| SIM | speechbrain ECAPA-TDNN (`speechbrain-spkrec-ecapa-voxceleb-embedding`, Apache-2.0 per the model card at the pinned revision) with the front end its `hyperparams.yaml` declares, loaded with strict keys from the hash-bound checkpoint; cosine per delivered chunk against the speaking voice's reference clip, wSIM minimum over 10 s windows (5 s hop). It runs on the CPU in an interpreter with torch and speechbrain named explicitly (the `ml` shell's, from nixpkgs; no lock change), 1 to 8 threads, one scorer at a time inside a 6G memory scope on the shared CPU host. The bench scorer checks the reference clip's current consent (`--config`), adds the bench plan's decoys 1 and 2 (decoy 2 from the decoy2 preset-voice passes only) and reads each arm, over its seed passes, against the preregistered SIM bars, with an all_met field that counts a missing value as unmet. `narrate evaluate` and the bench scorer share a one-scorer lock, and the MCP tool starts wer and sim inside the memory scope on Linux Why not ONNX: the bench had already pinned and licence-checked this checkpoint, torch is already in the `ml` shell, and an ONNX path would need a second model pin, onnxruntime in a shell and a reimplemented filterbank front end |
| SIM in render | not scored per take in v0 (`sim_not_measured` on every run); `evaluate` scores the delivered chunks. Gating takes on SIM waits for a calibrated `minSim` |

## Guitar axioms

The guitar axioms in AGENTS.md (low-end protection, no blanket high-pass,
musical-mistake review) govern guitar takes, not narration speech. Narration
ships no guitar default and no guitar tool reads a narration manifest.
