# Condense rebuild of the published v5 walkthrough cut (2026-10-15)

Authority: operator interview 2026-10-15 ("we like the video we produced"); Linear TIN-6544 (S4 milestone
"Condense on real talks"); R-HOOK-CONVERGENCE-20261004 R-N13.

The recordings, the archive, the private `talk.toml` and every work dir stay on the operator host. This
receipt records hashes, counts, versions and measured numbers only. The goal is a match within 1 frame, not
hash identity: a hand-run pipeline made v5.

## What talk.toml could not express, and what it can now

| v5 decision | Before | Now |
| --- | --- | --- |
| A-B-D order, card for the lost clip | `order`, `card` | unchanged |
| Intro: head 4x, welcome 1x, 2x rising to the 2.5x cap at `max_s` 480 | `zones`, `welcome`, `speed`, `speed_max`, `max_s` | unchanged |
| Phone clip: 1.25x for 240 s, then 2x | `zones` | unchanged |
| The 1:15-2:21 set-up stretch dropped (`A_DROP` in the hand-run script) | no key | `[[clip]] drop = [[start, end], ...]` |
| x265 `medium` | not checked | `[encode] preset`, checked against the preset names; default stays `slow` |
| YouTube copy: H.264, `-bf 0 -g 60`, `+faststart` | no key | `[encode] upload = "h264"` writes `talk.upload.mp4` and `talk.corrected.upload.mp4` |
| Four approved `*` corrections | `[[correction]]` | unchanged; `[rules] overlay_s = 3.5` sets v5's hold |

Each new key is validated when the config loads and has a synthetic test (`condense/tests/test_config.py`,
`test_edl.py`, `test_render.py`): bad, overlapping, out-of-order, too-short and past-the-end drop spans are
refused; a card clip takes no drop; a drop becomes one cut of 5 + 4 kept frames, an edge inside a pause cut
moves out to that cut's edge, the time map returns nothing inside it and its words leave the captions; the
upload copy is H.264 with `has_b_frames=0`, every packet's pts equal to its dts from 0, a keyframe every 60
frames, the edit's frame count and its audio stream bit-identical (md5), from the parts and from the edit; no
output path may be a clip file.

## Inputs

| Item | sha256 |
| --- | --- |
| Hand-run edit list `edl.v5.json` | `649bb675e5cc811801869f9392fef9c64b87690963a575efe33d0d17e6af8fd7` |
| Published v5 captions `-v5.srt` | `56855fd17b8ed51624e52cf7afed6d19d2ff17fa2f08ee0bd3f561ef8c7f7a45` |
| Hand-run `build_edl.py` (the `drop()` and `A_DROP` source) | `1ea68eade3c4b11a8e5fe45ffa7d13585d88d6e1fbfa9465ac107453464dc097` |
| Private v5 `talk.toml` (three clips, drop, `medium`, upload, 4 corrections, `overlay_s` 3.5) | `394736084675d97f1206d5d25a07c224404a049bbca0e09aad7450c2740493e0` |
| Recordings | the three TIN-6543 hashes (`2026-10-15-condense-parity.md`), hard-linked |

Versions: FFmpeg 8.1.2, whisper-cpp 1.8.4 (not run), Python 3.13.15, `nix develop .#condense`.

## Two tiers

The edit list depends on two things: the talk.toml decisions and the analysis (words, events, RMS, pause
re-reads). The two are measured apart.

- **Seeded tier**: the hand-run pipeline's own archived analysis (`intro`/`iphone` events, words, RMS and the
  pause re-read cache), converted to condense's file shapes, then `edl.build` and `captions` with the v5
  talk.toml. Whisper is not called; 0 pause spans were missing from the archived cache.
- **Tool tier**: condense's own analysis from the TIN-6543 all-clip run (whisper not re-run), then edl,
  render, captions and overlay with the v5 talk.toml.

A kept span is source time the edit plays: a speech, pause, filler or card segment, or one kept edge of a
cut. Spans are matched by source edges; "within 1 frame" means both edges within 1/30 s and the same speed.

### Edit list against `edl.v5.json`

`edl.json` sha256: seeded `3fdb0c65b4f265d9cb2e21c85cc34503802309460712958170394a1eccf48007`, tool
`767cfcacc3f14e275d0680855ea2e4dcaa47afbf2e415eadf8b8feeadc76d790`. Both validated by `video-utils timeline`.

| | v5 | Seeded tier | Tool tier |
| --- | ---: | ---: | ---: |
| `intro` kept spans within 1 frame | 2379 | 2377 of 2379 | 1467 of 2379 |
| `iphone` kept spans within 1 frame | 797 | 797 of 797 | 446 of 797 |
| `folds` card: source end, frames | 651.000 s, 600 | 651.018 s (0.54 frame), 600 | same as seeded |
| Segments intro / folds / iphone | 1802 / 1 / 625 | 1801 / 1 / 625 | 1768 / 1 / 621 |
| Total frames | 37531 | 37530 (-1) | 37725 (+194) |
| Drop cut | 75.300-141.067 s | 75.300-141.067 s | 75.300-141.233 s |

Seeded tier: every kept span matches within 1 frame except the intro's last two. The hand-run script ended
the intro at a hard-coded 3294.1 s; condense ends a clip with its shorter stream on the frame grid, 3294.133 s.
So the last cut's tail keep moves 2 frames and v5's final 1-frame speech segment joins the cut. The total is
1 frame short of v5. Of the 2427 segments both lists share, 1788 start on the same output frame and 639 one
frame earlier: the quantiser breaks a few rounding ties the other way.

Tool tier: the drop works (its end moves to 141.233 s because condense's own pause cut there ends 5 frames
later), but condense's own words and events differ from the hand-run ones: 1913 of 3176 kept spans match
and the total is 194 frames (6.47 s) longer. That is an analysis difference, not a talk.toml decision: on the
hand-run analysis the same talk.toml reproduces v5.

### Captions against `-v5.srt`

`talk.srt` sha256: seeded `e93a1401dc15f39846747150eb3b630ca5acb7f1c4faa4f24d4f7aa62603baaf`, tool
`ec8387f24f3ac9964615ee488c07c7deadca45fbfc895d7ba47c9b71ba34519c`.

| | v5 | Seeded tier | Tool tier |
| --- | ---: | ---: | ---: |
| Cues | 520 | 462 | 502 |
| Cue for cue within 1 frame | | 0 | 0 |
| Caption words aligned to v5's (difflib) | 5063 | 5023 (ratio 0.978) | 4487 (ratio 0.873) |
| v5 cue starts whose word lands within 1 frame | | 492 of 515 | 9 of 444 |

The words land where v5 put them (seeded tier), but no cue matches: the grouping differs. That is a gap, below.

### Corrections

Seeded-tier placements against v5's burned-in times: 470.333 / 963.006 / 1155.533 / 1161.933 s against
470.400 / 963.039 / 1155.567 / 1162.100 s: 2, 1, 1 and 5 frames early. A note inside a cut lands at the
join in condense and at the cut's end in the v5 script.

## Tool-tier render

Stages `edl`, `render`, `check silence loud`, `captions` and `overlay` on the v5 talk.toml, `[encode] jobs = 2`,
x265 `medium`. The `iphone` mezzanine was a reflink copy of the TIN-6543 run's (same code, same recording,
same encode settings); the `intro` mezzanine was built here. Render exit 0 in 3247 s, overlay exit 0 in
1003 s, on a shared host at load 45-105. Every file has 37725 video packets, the EDL's frame count, and the
same audio stream (md5 `45925b0dab592b91c429ef82cf379046`, AAC 64 kb/s mono, 1257.505 s).

| File | sha256 | Bytes | Video | pts = dts | Keyframes |
| --- | --- | ---: | --- | --- | --- |
| `talk.mp4` | `a0709eb86ccedfbad4f731425cc7e77ec294cf1865cf87be3b7fd4d423c2fb0b` | 44648311 | HEVC Main, `has_b_frames=2` | 26952 differ, first dts -1024 | x265 scene-cut |
| `talk.upload.mp4` | `79c1053e33ffc4e3ad9eec442af64f34c66760d6708b30502f0dc3b4d7ace439` | 490280801 | H.264 High, `has_b_frames=0` | all 37725, first pts 0 | every 60th packet, 629 |
| `talk.corrected.mp4` | `585bad9f47a3ef3ac137b81ae21c054b8cc4913b88a7900a6066db8a9d7b7559` | 44656677 | HEVC Main, `has_b_frames=2` | 26952 differ | x265 scene-cut |
| `talk.corrected.upload.mp4` | `21fd6f78d579502194920e49b6c6bc71c4a9cf139a00a9c57d84beee364076e8` | 490198009 | H.264 High, `has_b_frames=0` | all 37725, first pts 0 | every 60th packet, 629 |
| `talk.vtt` | `1cb77b407116d08fb353e854f2af76fab8941ba5ec898c8072b528f1ae87ea56` | | | | |

The upload copies' container layout matches the published v5 YouTube copy: one video edit list entry with
media time 0, one audio entry with media time 1024 (the AAC priming), no negative CTS and no packet with
pts different from dts. The published copy measures the same way (`has_b_frames=0`, 0 of 37531 packets with
pts != dts, first pts 0); the v5 HEVC archive copy has 27107 such packets and a first dts of -1024.

`check`: `silence` 0 hits at -35 dB over 1.0 s; `loud` -16.0 LUFS, true peak -1.0 dBTP. `sync` and `bounds`
were not run (a stand-in probe of the 55-minute clip and whisper re-reads; host load). No listening review.

The overlay placed the four notes at 469.21, 966.94, 1160.84 and 1166.93 s of this edit (the tool tier's
own timeline, which differs from v5's by the analysis difference above).

## Preset: slow against medium

`iphone` alone (the TIN-6543 iphone talk.toml and parts), the final join, two-pass loudness and encode only,
run one after the other at load 47-60. CPU time is the steadier number on a shared host.

| Preset | Wall s | CPU s (user + sys) | Bytes | SSIM against the lossless parts, same delivery filter |
| --- | ---: | ---: | ---: | --- |
| `slow` (default) | 1741.3 | 5014.3 | 15852955 | 0.971343 (15.43 dB) |
| `medium` | 337.3 | 1987.6 | 14554820 | 0.969213 (15.12 dB) |

The `slow` file is byte-identical to the TIN-6543 published `iphone` talk.mp4
(`ca339812e42b5008c125f76048e5ec6158ae196f9838d88173eb26b3c793d6bc`). At the same CRF, `medium` takes 40% of
the CPU and writes 8.2% fewer bytes at a lower SSIM, so it is a different point on the curve, not a free
win. The default stays `slow`, which also keeps the TIN-6543 parity hashes; a talk.toml that wants v5's
speed sets `preset = "medium"`, as the v5 one does.

## Gaps that stay

1. **Caption grouping.** v5's captions came from a one-off script: up to 84 characters, a break at a 1.2 s
   gap, at 6 s and at every sentence end, a 0.6 s minimum, and a card caption for the lost clip.
   `captions.py` holds 2 lines of 42 characters, breaks at a 1.0 s gap and only at sentence ends past half a
   line, and gives cards no caption. `captions.py` is outside this lane's files, so a `[captions]` style
   (and a card caption) is a follow-up, not a change made here.
2. **Correction placement and look.** v5 held the last note 4.0 s (the others 3.5 s), placed a note inside a
   cut at the cut's end and drew it at 40 px with a 0.6 box; condense holds every note `overlay_s`, places
   it at the join and draws at h/24 with a 0.65 box. Up to 5 frames of placement and the font size differ.
3. **Analysis.** The tool tier differs because condense's whisper passes and event rules are not the
   hand-run ones (TIN-6543 compared condense with the packaged tool, not with the hand-run scripts).
4. **Upload audio.** v5's YouTube copy re-encoded the audio as AAC 128 kb/s; the upload copy here copies
   the edit's 64 kb/s AAC, so it adds no generation loss.
5. **Descriptors.** `program/tools.json` and the frozen condense skills still list `talk.mp4` and
   `talk.corrected.mp4` only; `scripts/tool_api.py`'s write guard does not yet name the upload copies.
   `Config` now refuses any output path that is a clip file, upload copies included. Updating the frozen
   descriptors needs an admission revision.
6. **Publish.** `publish.py` does not copy the upload copies into a run. Not run here (TIN-6546 owns
   `condense-all` ending in a verified run).

## Old-tool full render (TIN-6543 note)

The new full render cannot be compared with a full render of the retired tool on this talk.toml: the retired
tool has no `drop`, `preset` check or upload copy, so it would cut a different edit. The comparable pair is
both tools on the TIN-6543 talk.toml without a drop, two more renders of the 55-minute clip on a host at load
60-100. Not run.

## Files outside this lane

`condense/overlay.py` (5 lines): the overlay pass writes `talk.corrected.upload.mp4` when `upload` is set,
because the v5 YouTube copy carried the corrections.

## Gates

- `just condense-lint`: ruff check and format check pass on 33 files. `just condense-test`: 127 passed.
- `tests/test_s4b_tool_admission.py`: 12 tests OK (1 skipped); no descriptor or skill changed.
  `tests/test_condense_public_surface.py`: OK.
- `just check` locally: 2014 tests, 27 failures and 6 errors, all in the known environment-only set
  (web: no offline pnpm mirror, 24; marked video/compact and arrangement markers: no installed font, 8;
  the capture adapter: an `inspection failure` under load, 1). This lane changes no root Python or Rust.
- Hosted CI on the code commit: `offline`, `condense`, `web` and `bazel` pass.
