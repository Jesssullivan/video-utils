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

Each new key has a synthetic test (`condense/tests/test_config.py`, `test_edl.py`, `test_render.py`). The
config refuses bad, overlapping, out-of-order and too-short drop spans when it loads (a cut keeps 9 frames,
so a span needs at least 10), a drop on a card clip, an unknown preset or upload, an `upload_crf` that is not
a whole number from 0 to 51, and any output path that is a clip file. A span that ends past the clip is
refused at the `edl` stage, which knows the clip's length. A drop becomes one cut of 5 + 4 kept frames; an
edge inside a pause cut moves out to that cut's edge (the end-edge case is the tool tier's 141.067 to
141.233 s); two valid spans that meet once an edge moves become one cut; the time map returns nothing inside
a drop and its words leave the captions; with `evidence = "asr"` whisper never reads a pause span inside a
drop. The upload copy is H.264 with `has_b_frames=0`, every packet's pts equal to its dts from 0, a keyframe
every 60 frames, the edit's frame count and its audio stream bit-identical (md5), from the parts and (with a
printed second-generation warning) from the edit; `render()` itself writes it only when `upload` is set.

## Inputs

| Item | sha256 |
| --- | --- |
| Hand-run edit list `edl.v5.json` | `649bb675e5cc811801869f9392fef9c64b87690963a575efe33d0d17e6af8fd7` |
| Published v5 captions `-v5.srt` | `56855fd17b8ed51624e52cf7afed6d19d2ff17fa2f08ee0bd3f561ef8c7f7a45` |
| Hand-run `build_edl.py` (the `drop()` and `A_DROP` source) | `1ea68eade3c4b11a8e5fe45ffa7d13585d88d6e1fbfa9465ac107453464dc097` |
| Private v5 `talk.toml` (three clips, drop, `medium`, upload, 4 corrections, `overlay_s` 3.5) | `394736084675d97f1206d5d25a07c224404a049bbca0e09aad7450c2740493e0` |
| Recordings | the three TIN-6543 hashes (`2026-10-15-condense-parity.md`), hard-linked |
| Converter of the hand-run analysis (seeded tier), `2026-10-15-condense-v5-seed-hand.py` | `140d0e0416769354749b772dcd7a5e527c87c8121ea44eee2f5fbb938194220a` |
| Edit-list comparison, `2026-10-15-condense-v5-compare-edl.py` | `002f13539be4f29699b545c6d02d6fbef090d0b72bc0be9d9e9d5a2533b7d7b6` |
| Caption comparison, `2026-10-15-condense-v5-compare-srt.py` | `6138a31728e2ebb6a85a7ff1619b3ec86de9ae8d65f7808aa24120a863bc3dd7` |
| SSIM against the lossless parts, `2026-10-15-condense-v5-ssim.py` | `594f172c31ce7f5f98e4b7f5979bcb56e0ccf5f4e6f254a0cfe9825261e90023` |
| Final join and encode only (preset timing), `2026-10-15-condense-v5-final-only.py` | `eb78b130427d09e3b2f40804d29273da95bad645660312261b33d43bfb2a8c40` |

The five scripts sit beside this receipt in `docs/agent-notes/` and, byte-identical, in the private parity
directory's `scripts/`. Four are the bytes that produced the numbers below. The edit-list comparison's
`match()` docstring was corrected on 2026-10-16 (it claimed a half-second window that the code never had;
the earlier bytes hashed `f4170c83...e0b615`); its code is unchanged. Re-run on 2026-10-16 from these files:
the converter rebuilt the seeded `edl.json` to the same sha256 (`3fdb0c65...`, 0 pause spans missing, no
`FIXED_WELCOME`), the tool-tier edl stage rebuilt `767cfcac...` with whisper stubbed to fail, and the two
comparisons printed the same counts as the tables below. The SSIM and preset scripts were not re-run (two
long encodes); their logs stay in the private preset run directory.

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
cut (two spans per cut). Matching rule (`compare-edl.py`, `match()`): one forward pass over v5's spans in
source order; for each, skip the new spans that end at or before it starts, take the next 5 candidates
around that point (indices j-2 to j+2), and pair it with the one whose |start difference| + |end difference|
is least. A pair counts "within 1 frame" when both edges differ by at most 1/30 s and the speeds by at most
0.1%. A new span may pair with more than one v5 span. The seeded-tier counts do not depend on the rule; the
tool-tier counts do: an independent order-tolerant matcher (review of 2026-10-16) found 1587 intro and 479
iphone matches where this one finds 1467 and 446, and on the seeded tier the same 2377, 797 and 37530 frames.

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

## TIN-6544 acceptance: not met as written

TIN-6544 stays open; this PR does not close it.

| Acceptance line | State |
| --- | --- |
| Every kept span within 1 frame of `edl.v5.json` | Seeded tier only (hand-run analysis): 2377 of 2379 and 797 of 797. With condense's own analysis from the TIN-6543 all-clip run, which the lane task named: 1467 of 2379 and 446 of 797 (matcher-dependent, above) |
| Total within 1 frame | Seeded tier only: 37530 against 37531. Tool tier: +194 frames |
| Captions cue for cue within 1 frame | Not met: 0 of 520 cues on either tier (gap 1) |
| No B-frames, no negative CTS for the upload | Met on both upload copies |
| Every decision a typed field with a test, or a recorded gap | Met: three typed keys, six gaps below |
| Rebuild with `just condense-all` | Not done: the stages ran one at a time (`edl`, `render`, `check silence loud`, `captions`, `overlay`), seeded from TIN-6543 analysis so whisper did not run; `publish` was not run (gap 6) |

## Gaps that stay

1. **Caption grouping.** v5's captions came from a one-off script: up to 84 characters, a break at a 1.2 s
   gap, at 6 s and at every sentence end, a 0.6 s minimum, and a card caption for the lost clip.
   `captions.py` holds 2 lines of 42 characters, breaks at a 1.0 s gap and only at sentence ends past half a
   line, and gives cards no caption. The cue grouping was deliberately left for a follow-up (a `[captions]`
   style and a card caption), so this PR changes no caption rule.
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

## Proposed follow-ups (not filed here)

This lane is read-only on Linear apart from one comment on TIN-6544, so these are proposals for the
integrator to file, not issues:

1. A `[captions]` style (characters per cue, gap and duration breaks, minimum cue length) and a card
   caption, so a talk.toml can reproduce v5's cue grouping (gap 1).
2. Name `talk.upload.mp4` and `talk.corrected.upload.mp4` in `program/tools.json`, the condense skills and
   `scripts/tool_api.py`'s write guard, through an admission revision (gap 5).
3. `publish.py` copies and hashes the upload copies into a run, and `verify-run` checks them (gap 6).

## Old-tool full render (TIN-6543 note)

The new full render cannot be compared with a full render of the retired tool on this talk.toml: the retired
tool has no `drop`, `preset` check or upload copy, so it would cut a different edit. The comparable pair is
both tools on the TIN-6543 talk.toml without a drop, two more renders of the 55-minute clip on a host at load
60-100. Not run.

## Files outside this lane

`condense/overlay.py` (5 lines): the overlay pass writes `talk.corrected.upload.mp4` when `upload` is set,
because the v5 YouTube copy carried the corrections. The five comparison scripts are new receipt files
beside this one; nothing imports or runs them.

## Gates

- 2026-10-15, code commit: `just condense-lint`: ruff check and format check pass on 33 files.
  `just condense-test`: 127 passed.
- 2026-10-16, review fixes: `nix develop .#condense -c just condense-lint condense-test`: lint passes,
  133 passed (six new tests).
- `tests/test_s4b_tool_admission.py`: 12 tests OK (1 skipped); no descriptor or skill changed.
  `tests/test_condense_public_surface.py`: OK.
- `just check` locally: 2014 tests, 27 failures and 6 errors, all in the known environment-only set
  (web: no offline pnpm mirror, 24; marked video/compact and arrangement markers: no installed font, 8;
  the capture adapter: an `inspection failure` under load, 1). This lane changes no root Python or Rust.
- Hosted CI on the code commit: `offline`, `condense`, `web` and `bazel` pass.
