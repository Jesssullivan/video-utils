# Talk condensing (`./condense`)

Authority: operator decision of 2026-10-15 (Linear initiative I-78, milestone
"Absorb talk-condense", TIN-6500 to TIN-6513), repository AGENTS.md and R-N13.

`condense/` condenses a recorded talk. Long pauses are cut. Short pauses and
fillers are sped up. Speech plays faster. No word is dropped unless the editor
drops a span. It is a speech
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
| render | `render.py` | `edl.json` | mezzanines, parts, `talk.mp4`, optional `talk.upload.mp4` |
| check | `check.py`, `avsync.py` | the edit | `check.json`; exit 1 when a gate fails or is not measured |
| captions | `captions.py` | words, `edl.json` | `talk.srt`, `talk.vtt` |
| overlay | `overlay.py` | `[[correction]]` entries | `talk.corrected.mp4`, optional `talk.corrected.upload.mp4` |
| publish | `publish.py` | the outputs and `edl.json` | `artifacts/condense/<run_id>/` with an `edl_v1` manifest |

`condense/README.md` gives every rule and default. `condense/config.py` holds
the defaults and `talk.toml` overrides them.

## Editor decisions in talk.toml

TIN-6544 rebuilt a published hand-cut walkthrough from a private talk.toml. Three
of its decisions had no key, and each is now typed, validated (when the config
loads, except where the table says otherwise) and covered by a synthetic test:

| Key | Decision | Checked |
| --- | --- | --- |
| `[[clip]] drop = [[start, end], ...]` | Remove source seconds, talk and all, as one cut each, before `max_s` raises the speed | at load: in order, apart, at least one frame longer than a cut's 9 kept frames, no card clip; at the `edl` stage: inside the clip |
| `[encode] preset` | The x265 preset of the edit (and the x264 preset of the upload copy); `slow` stays the default | one of the x264/x265 preset names |
| `[encode] upload = "h264"` | Also write `<out>.upload.mp4` (and `.corrected.upload.mp4`): H.264, no B-frames, a keyframe every 2 s, no negative CTS, `+faststart`, the edit's audio copied | `""` or `"h264"`; `upload_crf` a whole number 0 to 51; no output path may be a clip file |

`drop` is the one rule that removes words, so it is an explicit editor choice
per clip and never a default. The HEVC `talk.mp4` stays the archive copy. The
receipt `docs/agent-notes/2026-10-15-condense-v5-rebuild.md` records how close
the rebuild came and the decisions that remain gaps.

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

- `url` must be an `http` or `https` URL on a loopback host (an IPv4 or IPv6
  loopback address, or `localhost` while every address it resolves to is
  loopback) with no user info, no `;params` and no `#fragment`. A fragment
  would swallow the query the backend appends, so it is refused. A remote
  service needs an operator port forward. Proxies are bypassed and redirects
  are refused, so the token and the audio reach only that address.
- `http_timeout_s` must be a finite number above 0.
- The bearer token is read only from the `CONDENSE_STT_TOKEN` environment
  variable, and it is sent only when that variable is set. It must be visible
  ASCII with no space or line break; any other value (a trailing newline from
  an env file, say) is refused before any work, and the refusal does not echo
  it. It never appears in `talk.toml`, in `work/` or in an error message.
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
  back. `work/<clip>.stt.json` records the backend that produced them (the
  model file name, or the service URL), the language, the DTW preset, `pass1`
  and `chunk_s`; never the token.
- Fail closed: any HTTP status other than 200, a redirect, an unreachable
  service, a wait over `http_timeout_s` (3600 s), a reply over 64 MiB, invalid
  JSON or any other shape stops the stage. Nothing is retried. For both
  backends the stage first removes the clip's `pass1.json`, `dtw.json` and
  `stt.json`, and writes them only after both passes succeed, so a failed run
  leaves none behind, not even an earlier run's. `whisper_args` apply to
  whisper-cli only and are refused.
- `condense/tests/test_transcribe_http.py` runs an in-process fake service on
  synthetic media. Its `words.json` equals the whisper-cli path's for the same
  canned JSON. No real service has been contacted, so the tubebrain-stt request
  and reply shapes above are an unverified contract.
- The condense MCP tools are frozen at admission with `openWorldHint: false`,
  and `condense_transcribe` requires the registered model. Their talk.toml
  preflight refuses any `[whisper] backend` other than `cli`, and workers never
  receive `CONDENSE_STT_TOKEN`. That covers `condense_edl` and `condense_check`
  too, which call `read()`. Admitting the http backend under MCP needs a
  contract revision that declares it.

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

### check.json

TIN-6545. A `check` run of all four gates writes `work/check.json` (`kind`
`condense_check`, schema 1), whether its gates pass or fail; a run of fewer
writes `work/check.partial.json` and never replaces `check.json`. The report
lists the checks that ran (`complete` when all four gates did) and records per
gate its limits, measured values and verdict:

| Gate | Measured | Limit |
| --- | --- | --- |
| `silence` | hits at `silence_db` over `silence_s`, with output and source times | 0 hits |
| `loud` | integrated LUFS, deviation from the target, true peak, loudness range | 1 LU; true peak under 0 dBTP |
| `sync` probe | every frame of a coded stand-in, per clip: set-aside frames; min, median, max by window and by third | every frame within 20 ms |
| `sync` real | the delivered file at 1x speech against the mezzanine, per spot and per clip; medians by third of the edit | each measured clip's median within 20 ms |
| `sync` joined | the delivered file at up to 8 spots per third of the edit, at any speed, against the lossless parts | each third's median within 20 ms |
| `bounds` | the whisper match ratio at each cut and join; the text stays in the printed report | none; a person reads it |
| `captions` | cue start minus the nearest sound onset at up to 24 cues after a 0.3 s lead-in | none; measured, not gated |

`start`, `middle` and `end` are the thirds of the output timeline. Offsets are
in ms; positive means the sound leads the picture, or that the caption appears
after the speech starts. The file holds names, times and numbers only.

**No evidence, no pass.** A sync spot is clear when its sound correlates at
0.75 or more at a lag inside the 0.25 s search window and its picture match is
1.15 times better than the next frame. On the real talk the true matches
correlate at 0.80 to 0.99 (in sync and with an 87 ms lead); on the synthetic
talk with its sound moved 0.5 to 8 s early, beyond the window, every peak is
spurious at 0.57 or less, and on the real talk a 1 s lead leaves 0 of 33 spots
clear. A spot that is not clear is unclear for its sound (no match near the
picture, the sign of a gross offset) or, its sound clear, for its picture alone
(a slide, a screen recording or a still speaker gives no frame to time it by).
A median needs 4 clear spots. A real clip or joined third that tried 4 or more
spots and found fewer clear ones fails when its sound was unclear at so many
spots that fewer than 4 could have been clear; otherwise the picture kept them
from it, and it is `not_measured`, never `failed`: a talk in sync on a still
picture lacks evidence, it is not desynchronised. A clip or third with fewer
than 4 spots to try is `too_few_spots`; a real clip with no 1x speech, and a
joined third with only cards or parts under 60 frames, have nothing to measure.
All three are recorded and do not count. Each measure is `passed` only when
nothing failed or was `not_measured` and something passed; otherwise `failed`
or `not_measured`. Missing parts in `work/` make the joined measure
`not_measured`. The `sync` gate passes only when all three measures passed, so
an unmeasured gate fails the stage. `check.json` records every tried spot with
its offset, correlation, sharpness and `unclear` (`null`, `sound` or
`picture`), and per clip and third the tried, clear, sound-unclear and
picture-unclear counts, so a `failed` or `not_measured` verdict explains itself.

The report's `status` is `failed` when a gate failed, `not_measured` when none
failed but one lacked evidence, `partial` when every gate that ran passed but
not all four ran, and `passed` only for a complete run that passed.

**What it binds.** The report binds the sha256 of the delivered `talk.mp4` and
of `edl.json`, and nothing else. The `captions` measurement recomputes cues
from the words and times them against `talk.mp4`'s sound; it does not read the
delivered `talk.srt`. The captions and overlay stages write `talk.srt`,
`talk.vtt` and `talk.corrected.mp4` after `check`, so a published run's
captions and corrected copy are not what `check.json` measured.

`publish` carries a `check.json` that measured this very edit into the run as
an `output_sha256` file, so `verify-run` hashes it, and the manifest's `check`
records its sha256, `status` (the report's, so `partial` is never `passed`),
the gates and a summary. A `check.json` of another edit, or one that is not a
readable check report, is refused before anything is staged; without one
`check.status` is `not_run`. A partial report is never published, and a
`work/check.partial.json` of the same edit that is newer than `check.json` and
says `failed` or `not_measured` refuses the publish: `check.json` is stale. The
manifest's `status` stays `rendered_unreviewed`: a machine check is not a
listening review. `verify-run` reads the `check` object as an open field and
checks only the file's hash. When `verify-run` gives no verdict (it cannot
start, crashes or runs over the time limit), the run keeps its name and a file
`.unverified-<run_id>` beside it records why.

### Thresholds against a real talk

Measured on 2026-10-16 on the tool-tier v5 rebuild (TIN-6544; 37725 frames,
1257.5 s, three clips) with the review fixes, receipt
`docs/agent-notes/2026-10-16-condense-check-receipt.md`:

- **Sync, 20 ms: kept.** The coded probe's worst frame is 14.49 ms (sped
  phone speech; 8.79 ms in the room clip), the 1x real median +0.31 ms over 6
  of 9 spots, and the joined medians -5.05, -5.17 and -5.22 ms at the start,
  middle and end (6, 7 and 8 of 8 spots clear). The v2 bug, an 87 ms lead, is
  over four times the limit: on the real talk it reads +87.31 ms (real) and
  +81.95, +81.83 and +81.78 ms (joined), and fails; a 1 s lead fails with no
  clear spot (`condense/tests/test_check.py` repeats both on synthetic media).
  Single spots read one frame off (+28 to +34 ms, once -38.5 ms): 3 of 27 clear
  spots in this run, 7 of 54 joined spots over three runs of the measure, and
  3 of 12 in the worst run. So the limit applies to medians, never to one spot.
  Inference, not a measurement: if misreads were independent at the pooled
  rate (6 of 54 a frame late, 1 of 54 early), one third with 6 to 8 clear spots
  would fail falsely with a probability of 0.07 % to 0.4 %, about 0.7 % per run
  of three thirds; at the worst run's 3 in 12 it would be 3 % to 7 % per third.
  Unclear spots are a second source, which that estimate left out while the
  picture test alone could fail a measure. In the round-3 run every unclear
  spot near the sound was unclear for the picture only: 16 of 99 on the
  delivered, upload and 87 ms copies (sharpness 1.031 to 1.137, correlation
  0.853 to 0.989), none for the sound. Inference, assuming independent spots:
  at 16 in 99 a third of 8 or the real clip of 9 lacks 4 clear spots with a
  probability of 0.4 % or 0.1 %, about 1.3 % per run, which is now recorded as
  `not_measured`, never `failed`; at the 95 % upper bound of 3 in 99
  sound-unclear spots with the true match inside the window, a false `failed`
  from them is under 0.001 % per run. A still picture clusters its unclear
  spots, so a slide talk is `not_measured` far more often than that.
  Frame-exact reads would remove the misreads; they are a follow-up. The 1x
  real measure covers only the opening welcome here: the other clips play no
  speech at 1x.
- **Loudness, 1 LU: kept.** The delivered and upload copies both measure
  -16.0 LUFS (deviation 0.0 LU), loudness range 3.5 LU and true peak -1.0 dBTP:
  0.5 dB over the render's -1.5 dBTP target after AAC, 1.0 dB under the gate.
  The 11 s synthetic edit lands 0.4 LU off, so 1 LU is not loose for a short
  edit and two-pass linear loudnorm needs no tighter one for a long one.
- **Captions: not gated.** 15 of 24 sampled cues had a clear onset: median
  +135 ms, 90th percentile of |offset| 263 ms, range -215 to +280 ms. An energy
  onset is not a word onset (a breath or a click counts), so no limit is set
  until a reviewed set of cue starts exists.
