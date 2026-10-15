# condense

Condense a recorded talk. Long pauses are cut. Short pauses and fillers are sped up. Speech plays faster.
No word is dropped.

On one unpublished recording, the first edit made with these rules turned 74 minutes into 21 minutes.

This package came from `Jesssullivan/talk-condense` at commit `bf5b9dc` (see `../CHANGELOG.md`). The
repository-level rules are in `../docs/spec/CONDENSE.md` and `../AGENTS.md`.

## Quick start

Run these from the repository root.

```sh
nix develop .#condense                    # ffmpeg 8.1.2, whisper-cpp 1.8.4, python3, just, ruff, untrunc
just condense-model                       # the registered, hash-bound ggml-small.en model (465 MiB)
cp condense/examples/talk.toml talk.toml  # then name your recordings and set the speeds
just condense-all                         # every stage, then publish: a verified artifacts/condense/<run_id>/
just condense-lint condense-test          # lint and the synthetic-media tests, under a minute
```

`just condense-all` is the one command. It runs every stage below in order and ends in `publish`, which
runs `verify-run --timeline edl_v1`. It exits non-zero when a check gate fails or verify-run refuses the run.

Each stage is one recipe and one module in `condense/`. Each reads `talk.toml` and the files that the
stage before it left in `work/`. Run one stage again after you change a number.

| Recipe | Module | Reads | Writes |
| --- | --- | --- | --- |
| `just condense-recover REF BROKEN FIXED` | `recover.py` | a truncated `.mov` | a playable `.mov` |
| `just condense-transcribe` | `transcribe.py` | the recordings | `work/<clip>.16k.wav`, `.pass1.json`, `.dtw.json` |
| `just condense-events` | `events.py` | the whisper JSON | `work/<clip>.words.json`, `.events.json`, `.rms.txt` |
| `just condense-edl` | `edl.py` | words, events, RMS | `work/edl.json` |
| `just condense-render` | `render.py` | `edl.json` | `work/<clip>.mezz.mkv`, parts, `out/talk.mp4` |
| `just condense-check` | `check.py` | the edit | a report; exit 1 when a gate fails |
| `just condense-captions` | `captions.py` | words, `edl.json` | `out/talk.srt`, `out/talk.vtt` |
| `just condense-overlay` | `overlay.py` | `[[correction]]` entries | `out/talk.corrected.mp4` |
| `just condense-publish` | `publish.py` | the outputs, `edl.json` | `artifacts/condense/<run_id>/` with a manifest |

Recordings, transcripts and the model stay out of git. `.gitignore` lists them.

## The stages and their rules

Every number below is a default. `condense/config.py` holds them all. `talk.toml` overrides them.

### transcribe

whisper.cpp with the `ggml-small.en` model writes every word with a start time.

- The audio is extracted as 16 kHz mono. A clip with `normalize = true` also gets a high-passed and
  levelled copy for whisper. Use it for a noisy room.
- The clip is cut into chunks of about 800 s. Each cut sits in the longest silence near its target.
  One beam-search run over 55 minutes looped. Chunks did not.
- Each chunk runs twice. Pass 1 is the default beam search: it hears the most words, but its times can sit
  seconds off. The DTW pass is greedy with `-dtw small.en`: its word starts follow the audio, but it drops
  some words.
- The DTW pass always sets `-nfa`. Flash attention silently turns DTW off, and every `t_dtw` comes back -1.
  The stage fails when that happens.
- The model is registered by URL, size (487614201 bytes) and SHA-256 in `program/models.json`.
  `just condense-model` downloads and verifies it into `models/`. Nothing else downloads it.

### events

- Silences come from `silencedetect=noise=-32dB:d=0.6`. Set `silence_db` per clip. One room had a floor
  of -33 dB, so -32 dB found nothing there.
- RMS is measured in 100 ms frames.
- A pause is a silence, or a gap of more than 0.7 s between two words.
- A filler is any of these:
  - a filler word: um, uh, er, erm, ah, hmm, mm;
  - a "you know" or "I mean" stall;
  - the first copy of a run of 1 to 5 words said twice in a row, less than 3 s apart. `keep_repeats` lists
    single words that each clip doubles for emphasis ("very very");
  - an unworded burst: 0.15 to 1.5 s of sound between two silences that no word covers.
- Two cross-checks keep real words out of the unworded bursts:
  - DTW starts can run 0.6 s early. A word that ends up to 0.8 s before a burst still covers it.
  - The DTW pass drops words that pass 1 heard. A burst stays worded when pass 1 has a word within 1.5 s
    of it that the DTW pass lacks within 3 s.
- `detect = "phone"` is for a noisy room, where silencedetect finds nothing. Each word ends where its sound
  stops. Starts are the DTW onsets, even before their segment. There are no stalls. A repeat is 1 to 3
  words at any distance, and only the first copy's own words are sped. Gaps are read to 10 ms, and the
  silence before the first word is not a pause. These are the rules one unpublished phone recording was cut with.

### edl

Every span of every clip gets a kind and a speed.

| Kind | Rule | Speed |
| --- | --- | --- |
| welcome | the `welcome = [start, end]` window, fillers kept | 1x |
| speech | the clip's `speed`, or a zone's | 2x by default |
| pause over 1.0 s | cut; 5 frames before and 4 after stay (0.3 s) | removed |
| pause up to 1.0 s | sped up | 4x |
| filler | sped up, never cut | 8x |

- Events closer than 0.3 s merge into one span. The span is a pause when pauses cover half of it.
- Each span gives 0.15 s back to speech on both sides. Spans under 0.2 s stay speech.
- A cut joins its two kept edges with a hard video cut and a 2-frame audio crossfade.
- Anything at 4x or faster is turned down to 0.4 gain.
- Each welcome edge snaps to a pause edge within 1 s, so the 1x window clips no syllable.
- With `max_s` and `speed_max` set, the speech speed rises by 0.05 until the clip fits or the cap is reached.
- A clip ends with its shorter stream, so the last frames never freeze.
- Fillers are sped up and never cut. A wrong guess costs a blip, not a word.

Pause carving protects words that whisper missed or mis-timed. Inside a pause span, every run of 2 or more
RMS frames above `voiced_db` is a sound. A sound with evidence stays speech. A sound without evidence plays
as a filler. Only true silence is cut. `evidence` picks the proof:

- `energy`: any sound counts. For gated audio, where silence is digital silence.
- `word`: a transcribed word overlaps the sound. Only the filler lexicon is no proof, so a drawn-out "mmm"
  stays at speech speed.
- `asr`: that, or whisper re-run on the pause span alone hears a word. For noisy rooms. The answers are
  cached in `work/<clip>.pause_asr.json`.

`edl.py` also holds the time map. `Timeline.to_out(clip, source_s)` gives an output time, and
`Timeline.to_src(output_s)` goes back. Captions, overlays and checks all use it.

### render

1. Each recording becomes a mezzanine: constant 30 fps, 1280x720, mono 48 kHz PCM, x264 CRF 14. The video is
   padded with its last frame to the audio length. `tonemap = true` maps HLG phone footage to SDR.
2. The segments are split into parts of 220. Each part seeks its own window and runs one filter graph:
   `trim` and `setpts` for video, `atrim` and `atempo` for audio. `atempo` is chained in 2x stages.
   2 parts render in parallel by default (`[encode] jobs`). Every tool call stops after 7200 s
   (`CONDENSE_TOOL_TIMEOUT_S`).
3. The parts are joined. Each part's audio is cut or padded to its video frames first. Audio that runs 11 ms
   past the last frame would shift the next part by a frame.
4. Loudness takes two passes: one measures, one applies a single linear gain to -16 LUFS with a -1.5 dBTP
   ceiling. Speech peaks sit about 22 dB over its loudness. So a +9.5 dB gain into a -9.9 dBFS limiter runs
   first, and the linear gain then fits under the ceiling.
5. The encode is HEVC CRF 35 with the `hvc1` tag, so QuickTime, Safari and iOS play it. A light `hqdn3d`
   denoise runs first, because camera grain is most of the bitrate. Audio is AAC at 64 kb/s with
   `-aac_pns 0`: the encoder's noise substitution turned one transient into a +4.0 dBTP spike.

#### Sync

The first edit made with these rules drifted. Its sound ran up to 107 ms off the picture, and its first
part rendered 845.2 s from 834.9 s of EDL. Six rules fixed it. After them, the probe put every frame of that
part within 10 ms.

1. Every segment is a whole number of frames. The EDL rounds the running total, so the error stays under
   half a frame and never builds up. A segment that rounds to zero frames joins a neighbour. Its video and
   its audio are both built to exactly that length: `frames` video frames and `frames * 1600` samples.
2. Video is trimmed by time with a half-frame guard, then an even `select` keeps exactly that many frames,
   then `setpts=N/(30*TB)` numbers them. No `setpts=(PTS-STARTPTS)/speed`, and no inner video concat at cuts.
3. Audio runs `aresample=async=1:first_pts=0` before `asplit`, so a sample's index is its time. Each part
   seeks 1 s early. Samples are never counted from a seek point, because a seek lands mid-packet.
4. `atempo` runs at source frames / output frames, not at the nominal speed. It gets 0.2 s of extra source,
   because its tail runs up to 30 ms short or long. Then `apad` and `atrim=end_sample` fix the length.
5. Each clip has a `shift`: its audio stream's start after its video's, rounded up to frames. One recording's
   sound started 87 ms after its picture. The analysis wav starts at the first sample, so every time in the
   EDL is read at `time + shift` of the source: 3 frames there.
6. The limiter runs with `latency=1`, so it does not delay the sound. The mp4 is written with
   `-movflags +faststart+negative_cts_offsets`, so its video starts at 0 without an edit list. A player that
   ignores edit lists would otherwise show the video 2 frames late.

`avsync.py` measures it. See `check` below.

A mezzanine is reused when it is newer than its recording. Delete `work/*.mezz.mkv` after you change the
frame size or rate.

### check

- `silence`: the gate. `silencedetect` at -35 dB must find no silence of 1.0 s or more in the edit. Each hit
  prints with the source time it came from.
- `loud`: integrated loudness within 1 LU of the target, and a true peak under 0 dBTP.
- `sync` (`avsync.py`), within 20 ms:
  - probe: each clip gets a stand-in mezzanine. Its frame k shows k in 20 bits, and each audio sample holds
    its own time. The real part graphs run on it and are joined as the render joins them. Every output frame
    then tells which source frame it shows and which source time it plays. Each frame must be within 20 ms.
    A cut's 2 crossfade frames blend two times, so they are set aside.
  - real: at 1x speech in the delivered file, each picture is matched against 25 mezzanine frames near the
    EDL's answer, and 0.4 s of sound is cross-correlated 0.25 s to each side. The median per clip must be
    within 20 ms. This part sees the source's own clocks, `atempo`, the encode and the mp4 timestamps.
- `bounds`: whisper re-reads 6 s of the edit around two cuts per clip and around every clip join. It also
  reads the same span of the source. Both print side by side. A person reads them: a cut must not eat a word.

`just condense-check talk.toml silence loud` runs only the named checks.

### captions

Each word's source times go through the time map, so the captions sit on the output clock at the edit's
speed. A word is dropped when it is a filler, when it sits in a span that plays as a filler, or when the edit
plays none of it at speech speed. A caption holds at most 2 lines of 42 characters. It ends at a sentence
end, at a gap of 1 s, or when it is full.

### overlay

A correction is a short note for a moment where the speaker says something wrong:

```toml
[[correction]]
clip = "intro"
source_s = 312.4   # when it was said: seconds into the recording's sound, the transcript's clock
text = "*the queue holds 64 items, not 32"
```

The time map moves each note to the output clock. It shows for 3 s in the top right corner. A note that
lands in a cut moves to the join. Two notes never overlap.

The overlay is its own pass, so the main render is not repeated. The video is encoded once more, from the
parts in `work/` when they are still there. The audio stream is copied.

## Recover a truncated .mov

A recording that was cut off (a full disk, a crash) has no `moov` atom, and nothing will play it.
`untrunc` rebuilds the index from a healthy recording made by the same device and app.

```sh
just condense-recover healthy.mov broken.mov fixed.mov
```

- The reference must be a long recording with the same encoder settings. A 41 MB reference rebuilt 27% of
  a 977 MB file. A 4.9 GB reference from the same session rebuilt all of it: 10 min 51 s.
- `untrunc` exits 1 even on a full rebuild. The recipe reads the `Found N packets` and `Duration` lines
  and compares the output size with the broken file. It fails when under 90% of the bytes came back.
- The rebuilt audio can be longer than the video: 651.0 s against 643.8 s in that file. The mezzanine step
  pads the video to match.

## Layout

```
condense/          one module per stage, plus config.py, audio.py and avsync.py
condense/tests/    pytest on media that ffmpeg generates at test time
condense/examples/ every per-video setting in talk.toml
just/condense.just one recipe per stage
```

## Publish

`just condense-publish` copies the edit, `edl.json` and whichever captions and corrected copy exist into a
fresh `artifacts/condense/<run_id>/`. Its `manifest.json` hashes every file and every recording, and its
timeline mapping is `edl_v1`: output time maps to source time through `edl.json`
(`../docs/spec/TIMELINE_CONTRACT.md`). The stage then runs `video-utils verify-run --timeline edl_v1` on the
run. A run that fails the check is renamed to `.failed-<run_id>` and the stage exits 1. Guitar tools never
list or accept these runs. `just condense-all` ends in this stage. To check a published run again:

```sh
just verify-run artifacts/condense/<run_id> edl_v1
```
