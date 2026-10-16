# Condense check receipt: measured sync and loudness on a real talk (2026-10-16)

Authority: Linear TIN-6545 (S4 milestone "Condense on real talks"); repository AGENTS.md;
R-HOOK-CONVERGENCE-20261004 R-N13. The recordings, the private `talk.toml`, the work dir, every log and the
published run stay on the operator host. This receipt records hashes, counts, versions and measured numbers
only.

The sections from "What changed" to "Gates" record the first pass (commit `7304e8a`). The review fixes at
the end supersede them where they differ: the first pass let the sync gate pass without evidence, and
published a partial check as `passed`.

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

## Review fixes (2026-10-16, second pass)

### Defects fixed

1. **The sync gate passed without evidence (measured, synthetic, at `7304e8a`).** With an 8 s audio lead
   the real measure had 0 of 5 spots clear and the joined measure 0 of 24, all three thirds empty, and
   `check(["sync"])` returned true. Leads beyond the 0.25 s search window were judged on spurious matches:
   at 1 s and 3 s every sound peak correlated at 0.57 or less, against 0.88 to 0.98 for the true match at
   87 ms, yet 0.5 passed as clear. A missing set of parts returned `passed` with `measured` false; the
   private `check-pass2.json` shows that state on the real talk.
2. **A partial check was published as `passed`.** `check talk.toml silence loud` then `publish` gave
   `check.status` `passed` with `complete` false, and a partial run overwrote a complete `check.json`.

### What changed

- `condense/avsync.py`: a spot is clear at a sound correlation of 0.75 or more at a lag inside the search
  window (a peak on the window edge counts as 0) and a picture sharpness of 1.15. A median needs 4 clear
  spots (`MIN_CLEAR`). A real clip or joined third that tried 4 and found fewer fails; one that could try
  fewer is `not_measured`; a clip with no 1x speech and a third with only cards or short parts are recorded
  as having nothing to measure. Each measure reports a `verdict` (`passed`, `failed`, `not_measured`) and
  passes only when nothing failed and something passed. Missing parts give `not_measured`. The joined
  measure now tries up to 8 distinct frames per third, spread over that third's usable frames, and skips
  card parts; before, clamping in short parts measured the same frame up to four times.
- `condense/check.py`: the sync gate's verdict combines the three; `not_measured` fails the stage. The
  report has `status` (`passed`, `partial`, `not_measured`, `failed`) and `not_measured`. All four gates
  write `work/check.json`; fewer write `work/check.partial.json` and leave `check.json` alone.
- `condense/publish.py`: the manifest's `check.status` is the report's status, so a partial report reads
  `partial`, never `passed`. A truncated, non-object or malformed `check.json` is refused with a
  `RuntimeError` before staging, not a traceback. A verify-run with no verdict leaves
  `.unverified-<run_id>` beside the run with the reason.
- Docs: `docs/spec/CONDENSE.md` (no evidence, no pass; statuses; what `check.json` binds; thresholds with
  the false-fail estimate) and `condense/README.md`.

### Tests (synthetic media only)

New: a 1, 3 and 8 s lead each fail the sync gate with every measured third and the real clip `failed`, and
no clear spot under 0.75; missing parts leave sync `not_measured` and the stage failing; `judged` and
`overall` on spot counts; a partial run never replaces `check.json`; a complete check is published as
`passed`; a partial report is published as `partial` (also without a `status` field), never `passed`; four
broken `check.json` files are refused with nothing staged; a usage error, a crash and a timeout each leave
`.unverified-<run_id>`. On the synthetic edit the end third holds only the card and short parts, so it has
nothing to measure; the start and middle carry 7 and 8 of 8 clear spots in sync.

### Real talk, same inputs

Script `2026-10-16-condense-check-fix.sh` (sha256
`d69cbc6f005bff9b11841638fd422ae1b55cd5c6335b1b896249bba3a58ad78d`), same private run dir, inputs and
versions as above, `WHISPER_MODEL` the registered model (sha256 `c6138d6d...c41e5d`). The first
`check.json` is kept as `check-v1.json` (`7e1760d5...`). Host load 10 to 50.

`check` exit 0 in 465 s wall. `check.json` sha256
`f99a795337b57ea56297e138d0a9ebbb156ef4e10ce92624c6f3ac163a4fcf37`, `status` `passed`, `complete` true.
Silence, loudness, probe, bounds and captions read as in the first pass.

| Copy | Real (intro, 1x) | Joined start / middle / end (clear of 8) | Verdict |
| --- | --- | --- | --- |
| delivered | +0.31 ms, 6 of 9 clear | -5.05 (6) / -5.17 (7) / -5.22 ms (8) | passed |
| upload | +0.31 ms, 6 of 9 | -5.08 (7) / -5.12 (8) / -5.22 ms (8); -16.0 LUFS, -1.0 dBTP | passed |
| delivered, sound 87 ms early | +87.31 ms, 6 of 9 | +81.95 (6) / +81.83 (7) / +81.78 ms (8) | failed |
| delivered, sound 1 s early | 0 of 9 clear | 0 of 8 / 0 of 8 / 0 of 8 | failed |

Folds (card) and iphone have no 1x speech. Clear-spot correlations: 0.899 to 0.989 in sync, 0.799 to 0.984
with the 87 ms lead. Reports: `check-fix-upload.json` `33c8e424...a541a176`, `check-fix-lead87.json`
`62d03e45...4b038`, `check-fix-lead1000.json` `22d1e296...57558` (the moved copies were deleted after
measuring). Publish: `4 files, 37725 frames, check passed, verified`; manifest sha256
`00b973aabc1b7aacce29a792425196d2a3d28487b143ca632344aaf2bc9b7317`, `check.status` `passed`, `complete`
true, five gates true.

### One-frame reads and the 20 ms limit

Misread spots (one frame off): this run 3 of 27 clear (+33.69 real, +28.37 twice joined); joined over three
runs 7 of 54 (6 late, 1 early); the worst run 3 of 12. Inference, not measured: with independent misreads at
the pooled rate, a third with 6, 7 or 8 clear spots fails falsely with probability 0.20 %, 0.40 % or 0.07 %,
about 0.7 % per run; at 3 in 12 it is 3.8 %, 7.1 % or 2.7 % per third. The limit stays at 20 ms; frame-exact
reads are a follow-up that has no tracker issue yet.

### Still open

- The tool descriptor (`program/tools.json`, `condense_check`: "a printed report only", "sync (probe and
  real)") and the frozen `.agents/skills/condense-check/SKILL.md` do not name `check.json`, the joined
  measure or `not_measured`. Both are hash-pinned by `tests/test_s4b_tool_admission.py`, so the change
  needs an admission revision. This lane may not file tracker issues; it asks the integrator to file one,
  with frame-exact reads as a second.
- `check.json` binds `talk.mp4` and `edl.json` only. `talk.srt`, `talk.vtt` and `talk.corrected.mp4` are
  written after `check` and are not measured by it (stated in `docs/spec/CONDENSE.md`).

### Gates (second pass)

- `nix develop .#condense -c just condense-lint condense-test`: lint clean, 131 passed.
- `tests/test_s4b_tool_admission` and `tests/test_public_tree` in the condense shell: 16 tests OK, 1
  skipped.
