# Condense check receipt: measured sync and loudness on a real talk (2026-10-16)

Authority: Linear TIN-6545 (S4 milestone "Condense on real talks"); repository AGENTS.md;
R-HOOK-CONVERGENCE-20261004 R-N13. The recordings, the private `talk.toml`, the work dir, every log and the
published run stay on the operator host. This receipt records hashes, counts, versions and measured numbers
only.

## What changed

- `condense/check.py`: each gate measures, prints, and returns its limits, measured values and verdict.
  `check` writes `work/check.json` (`kind` `condense_check`, schema 1) whether the gates pass or fail,
  bound to the sha256 of the delivered file and of `edl.json`. A `captions` measurement (not a gate) times
  cue starts against sound onsets. `silence()`, `loud()`, `sync()` and `bounds()` still return booleans.
- `condense/avsync.py`: `measure_probe` and `measure_real` return per-clip summaries and the start, middle
  and end thirds. New `measure_joined`: 24 spots spread over the whole edit, at any speed, against the
  lossless parts the final step joined. The sync gate now also needs each joined third's median within 20 ms.
- `condense/publish.py`: a `check.json` that measured this very edit is published as an `output_sha256` file
  (so `verify-run` hashes it), and the manifest's `check` records its sha256, `passed`/`failed`, the gates
  and the summary; a `check.json` of another edit is refused; without one `check` is `{"status":
  "not_run"}`. The manifest `status` stays `rendered_unreviewed`. The video-utils binary is found before
  anything is staged. Only verify-run's exit 1 (a verdict) renames a run `.failed-<run_id>`; a timeout, a
  failure to start, a usage error or a crash leaves the run under its name, unverified, and the stage
  exits 1 saying "unverified, not refused".
- `verify-run` (Rust) is unchanged: the manifest's unknown fields are open, and `check.json` is bound
  through `output_sha256`. Tests in `condense/tests/test_publish.py` show a tampered `check.json` fails it.
- Docs: `docs/spec/CONDENSE.md` (check.json table, thresholds against the real talk) and the check and
  publish paragraphs of `condense/README.md`.

## Tests (synthetic media only)

`condense/tests/test_check.py`: the report binds the edit and records every measurement; a missed loudness
target is recorded as failed; unknown check names are refused; the v2 bug reintroduced (the in-sync edit's
sound moved 87 ms early) fails the sync gate: real median +87 ms within 3 ms, every joined third +87 ms
within 3 ms, while the coded probe still passes. `condense/tests/test_publish.py`: the check report is
published, hash-bound and summarised; a stale report is refused with nothing staged; no binary stages
nothing; a refusal (exit 1) renames `.failed-`; a usage error (exit 2), a crash (SIGKILL) and a timeout keep
the run's name, and the timed-out run then passes `verify-run`.

## Inputs

| Item | sha256 |
| --- | --- |
| Base commit (`origin/main`) | `4426f14c31141aff3c62d21fd919efc6890c7d0b` |
| Private v5 `talk.toml` (TIN-6544 receipt) | `394736084675d97f1206d5d25a07c224404a049bbca0e09aad7450c2740493e0` |
| `talk.mp4` (tool tier, TIN-6544) | `a0709eb86ccedfbad4f731425cc7e77ec294cf1865cf87be3b7fd4d423c2fb0b` |
| `talk.upload.mp4` (tool tier, TIN-6544) | `79c1053e33ffc4e3ad9eec442af64f34c66760d6708b30502f0dc3b4d7ace439` |
| `edl.json` (tool tier) | `767cfcacc3f14e275d0680855ea2e4dcaa47afbf2e415eadf8b8feeadc76d790` |
| `talk.srt` (tool tier) | `ec8387f24f3ac9964615ee488c07c7deadca45fbfc895d7ba47c9b71ba34519c` |
| Run script `2026-10-16-condense-check-real.sh` | `49724234244edede46317893da8d572ed11dac07e0a14208b04b1bf00631b989` |
| Diagnostic `2026-10-16-condense-check-diag-split.py` | `164d7c279b2d7fdc0edde0e6da5b7c55c1e54bea3191d6a5a6dc2375fb6934a6` |
| Diagnostic `2026-10-16-condense-check-diag-seek.py` | `4d03402a5973f2bdbc29ea118843644661355353f0141557ea2fffe05cc55f81` |

The inputs are reflink copies of the TIN-6544 tool-tier work dir in a separate private run dir, so that
lane's files are unchanged. The scripts sit beside this receipt and take every path as an argument. Versions:
FFmpeg 8.1.2, whisper-cpp `ggml-small.en` (the registered model, `bounds` only, 4 threads), Python 3.13.15,
`nix develop .#condense`, `[encode] jobs = 2`. The edit: 37725 frames, 1257.5 s, clips intro, folds (card)
and iphone.

## Results

`check` exit 0 in 556 s wall at host load 15-33. `check.json` sha256
`7e1760d56ae1a71a119152fd4415367baa17a70477d002abc9e4bdaa53500f92`, `complete` true, `passed` true.

| Gate | Measured | Limit | Verdict |
| --- | --- | --- | --- |
| silence | 0 hits | 0 at -35 dB over 1.0 s | pass |
| loud | -16.0 LUFS (deviation 0.0 LU), true peak -1.0 dBTP, range 3.5 LU | 1 LU, under 0 dBTP | pass |
| sync probe, intro | 24947 frames, 1146 set aside; all -8.79 to +8.04 ms, median 0.00; 1x -0.33 to +0.67; sped -8.79 to +8.04 | every frame 20 ms | pass |
| sync probe, iphone | 12178 frames, 352 set aside; all -13.45 to +14.49 ms, median 0.00; 1x 0.00 to +0.33; sped -13.45 to +14.49 | every frame 20 ms | pass |
| sync real (1x) | intro +0.31 ms median over 6 clear spots (3 unclear), all in the first 28 s; folds and iphone: no 1x speech | median 20 ms | pass |
| sync joined | 21 of 24 spots clear; start -5.05 ms (8), middle -5.17 ms (7), end -5.12 ms (6) | each third's median 20 ms | pass |
| bounds | match 0.87, 0.62, 0.13, 0.02, 0.96, 0.48 at two intro cuts, the two joins and two iphone cuts | none; a person reads it | recorded |
| captions | 502 cues, 171 after a 0.3 s lead-in, 24 sampled, 15 clear: median +135 ms, p90 of abs 263 ms, -215 to +280 ms | none | measured |

The low bounds ratios at the two joins are the card (no speech in the edit) and the clip change; they are
text for a person, not a verdict.

Upload copy (`check.upload.json` sha256 `b64727db7cddf396c790d9dab8a2fa85118cba090e77f109189162af558975c5`):
-16.0 LUFS, deviation 0.0 LU, true peak -1.0 dBTP, range 3.5 LU; real median +0.31 ms; joined 23 of 24 clear,
start -5.05, middle -5.37, end -5.29 ms; captions median +135 ms.

Publish into a private root: `4 files, 37725 frames, check passed, verified` (`talk.mp4`, `edl.json`,
`talk.srt`, `check.json`; manifest sha256 `1ebc20b882c59cd05359c9d794d8c6c8ad63128a881d50407bf96a3a0daed96c`). The manifest's `check` names
`check.json` with the sha256 above, `status` `passed`, `complete` true and all five entries true.

## Thresholds

- Sync 20 ms: kept. Worst probe frame 14.49 ms; real and joined medians within 5.4 ms; the 87 ms v2 lead is
  4.35 times the limit and fails it. 3 of 27 clear spots read one frame off (+28.42, +33.69, -38.54 ms), so
  the limit stays on medians.
- Loudness 1 LU: kept. 0.0 LU on both copies; the synthetic 11 s edit lands 0.4 LU off. True peak sits 0.5 dB
  over the render's -1.5 dBTP target and 1.0 dB under the 0 dBTP gate.
- Captions: not gated (no reviewed cue starts; an energy onset is not a word onset).

## Findings

1. **A constant -5 ms sound lag after the first part (measured; cause inferred).** Split diagnostic (12
   spots, earlier pass): the picture matched the expected part frame, and the sound sat -0.3 ms in part 0
   and -4.7 to -5.6 ms in parts 1 to 12, without drift. The delivered audio stream lasts 1257.505 s against
   1257.500 s of video. Inference, not verified: one part join pads about 5 ms of sound. The coded probe does
   not see it. Within the limit; a render follow-up, outside this lane.
2. **One-frame picture reads (measured).** The seek-based frame reads land one frame off at some spots, in
   both the HEVC and the H.264 copy. Reading the same spot by decode order (`select=n`) found the expected
   frame at 157.17 s; the seek diagnostic showed the delivered file's seek read differing from decode order
   by one frame at 4 of 4 spots and the part's at 1 of 4. 12 joined spots let two such reads move the end
   third's median to +11.56 ms; 24 spots give -5.12 ms. Frame-exact reads are a follow-up.
3. **Coverage.** The 1x real measure only reaches the intro's welcome: the phone clip plays no speech at
   1x. The joined measure covers the whole edit but not atempo's own timing inside a sped segment, which no
   instrument measures.
4. **Captions late by a median 135 ms (measured, energy onsets).** Not a gate; a reviewed set of cue starts
   is needed before a limit.
5. **Frozen descriptors.** `program/tools.json` and the frozen condense-check and condense-publish skills
   still say "a printed report only" and do not name `check.json`; changing them needs an admission
   revision. `check.json` is written beneath `work/`, inside the admitted write paths.

## Gates

- `nix develop .#condense -c just condense-lint condense-test`: lint clean, 120 passed (final code).
- `tests/test_s4b_tool_admission` in the condense shell: OK.
- `just check`: 2018 tests, 26 failures and 6 errors, all in the known environment-only set (no supported
  installed font for marked-video previews; no web pnpm offline mirror). `test_public_tree` passed.
- No Rust change, so `just test-rust` was left to hosted CI.

Process note: this lane stopped its own two check processes once, to rerun the measurement from the
committed script; no other session's process was touched.
