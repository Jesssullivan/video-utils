# Talk condensing (`./condense`)

Authority: operator decision of 2026-10-15 (Linear initiative I-78, milestone
"Absorb talk-condense", TIN-6500 to TIN-6513), repository AGENTS.md and R-N13.

`condense/` condenses a recorded talk. Long pauses are cut. Short pauses and
fillers are sped up. Speech plays faster. No word is dropped. It is a speech
workflow beside the guitar workflow, not a guitar default.

## Source

The code comes from `Jesssullivan/talk-condense` at commit `bf5b9dc`. The move
keeps every module byte-identical; only the package name changes from
`talk_condense` to `condense`. `CHANGELOG.md` records the migration, and the
receipt in `docs/agent-notes/` records a per-file comparison.

## Stages

| Stage | Module | Reads | Writes |
| --- | --- | --- | --- |
| recover | `recover.py` | a truncated `.mov` and a healthy reference | a playable `.mov` |
| transcribe | `transcribe.py` | the recordings | 16 kHz analysis wav, whisper pass-1 and DTW JSON |
| events | `events.py` | the whisper JSON | words, events, 100 ms RMS frames |
| edl | `edl.py` | words, events, RMS | `edl.json` |
| render | `render.py` | `edl.json` | mezzanines, parts, `talk.mp4` |
| check | `check.py`, `avsync.py` | the edit | a report; exit 1 when a gate fails |
| captions | `captions.py` | words, `edl.json` | `talk.srt`, `talk.vtt` |
| overlay | `overlay.py` | `[[correction]]` entries | `talk.corrected.mp4` |
| publish | `publish.py` | the outputs and `edl.json` | `artifacts/condense/<run_id>/` with an `edl_v1` manifest |

`condense/README.md` gives every rule and default. `condense/config.py` holds
the defaults and `talk.toml` overrides them.

## Ownership in this repository

- FFmpeg owns decode, filter, encode and loudness measurement.
- whisper.cpp owns transcription. It runs from the `condense` dev shell, and its
  `ggml-small.en` model is registered by URL, size and SHA-256 in
  `program/models.json`. Nothing downloads it implicitly.
- Bounded Python owns analysis: events, pause carving, speed choice and checks.
- Rust owns the timeline: EDL validation, frame quantisation and the
  source-to-output time map (`src/timeline.rs`, `video-utils timeline`), and
  run verification (`video-utils verify-run --timeline edl_v1`). The edl stage
  validates every `edl.json` it writes with `video-utils timeline validate`.
  `edl.py` keeps an in-process copy of the map and quantiser for the per-word
  loops in captions, overlay and check; `condense/tests/test_timeline_parity.py`
  requires its answers to equal the Rust ones exactly.
- Every stage gets a typed tool in `program/tools.json` and a skill under
  `.agents/skills/`, admitted in its own PR.

## Optional HTTP speech-to-text backend

TIN-6514. `[whisper] backend = "cli"` is the default and runs whisper-cli as
above. `backend = "http"` sends the same 16 kHz mono chunks to a speech-to-text
service instead, such as a local tubebrain-stt. TubeBrain stays a separate
product; no code moves between the repositories.

- `url` must be an `http` or `https` URL on a loopback host (`localhost` or
  an IPv4 or IPv6 loopback address) with no user info. A remote service needs an operator
  port forward. Proxies are bypassed and redirects are refused, so the token
  and the audio reach only that address.
- The bearer token is read only from the `CONDENSE_STT_TOKEN` environment
  variable, and it is sent only when that variable is set. It never appears in
  `talk.toml`, in `work/` or in an error message.
- Request: `POST <url>?response_format=whisper_full&language=..&prompt=..[&dtw=<preset>]`
  with the chunk as an `audio/wav` body. The DTW pass adds `dtw`; `read()` sends
  neither `prompt` nor `dtw` and joins the segment texts.
- Reply: HTTP 200 with whisper-cli's `-ojf` JSON (`transcription[].offsets` and
  `tokens[].{text, offsets, t_dtw}`). A reply shaped
  `{"segments": [{start, end, text, words: [{start, end, word}]}]}` in seconds
  is adapted to one token per word, and the word start stands in for the DTW
  time. That substitution is an inference, not a measured equivalence.
- `events.words_from` reads both backends unchanged. The pass-1 and DTW JSON
  land in `work/` as before, and the stage still fails when no DTW time came
  back.
- Fail closed: any HTTP status other than 200, a redirect, an unreachable
  service, a wait over `http_timeout_s` (3600 s), a reply over 64 MiB, invalid
  JSON or any other shape stops the stage. Nothing is retried and no partial
  JSON is written. `whisper_args` apply to whisper-cli only and are refused.
- `condense/tests/test_transcribe_http.py` runs an in-process fake service on
  synthetic media. Its `words.json` equals the whisper-cli path's for the same
  canned JSON. No real service has been contacted, so the tubebrain-stt request
  and reply shapes above are an unverified contract.
- The MCP tool `condense_transcribe` is frozen at admission. It still requires
  the registered model and declares `openWorldHint: false`. Running the http
  backend through it is not part of that contract yet.

## Rules that differ from the guitar workflow

- Speech delivery targets -16 LUFS and -1.5 dBTP. Guitar masters keep -18 LUFS.
- The 80 Hz high-pass and levelling apply only to the copy whisper reads.
- Condense time-stretches. Its runs carry an `edl_v1` timeline mapping
  (`docs/spec/TIMELINE_CONTRACT.md`) and are written under `artifacts/condense/`,
  so no guitar tool lists or accepts them.
- Recordings, transcripts, renders and the model stay out of git.

## Gates

`just condense-test` runs ruff and the pytest suite on media that FFmpeg
generates at test time; it needs no model and no recording. The CI `condense`
job runs it in the `condense` dev shell. `check` gates a real edit: no silence
of 1.0 s or more at -35 dB, loudness within 1 LU, a true peak under 0 dBTP, and
picture and sound within 20 ms. Listening quality and ASR accuracy are not
claimed by any gate.
