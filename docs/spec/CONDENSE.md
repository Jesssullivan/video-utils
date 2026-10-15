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
  run verification (`video-utils verify-run --timeline edl_v1`).
- Every stage gets a typed tool in `program/tools.json` and a skill under
  `.agents/skills/`, admitted in its own PR.

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
