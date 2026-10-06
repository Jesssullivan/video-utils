# S2 tone_ab: stage-attributed low-end and thin/nasal balance matched A/B

Lane `tone_ab`, sprint 20261006-s2, Linear TIN-5601 (parent TIN-5599, related
TIN-5487). Branch `sprint/20261006-s2/tone_ab`, baseline 4b87484. Authority:
operator S2 resume prompt, repository AGENTS.md, R-HOOK-CONVERGENCE-20261004
(R-N11/R-N12/R-N13). This is the Phase 1 contract freeze. No numerics ran
before this commit, which seals the preregistration below.

## Question and scope

The operator reports that the processed take lacks low-end fullness and sounds
thin/nasal. This lane measures where low-band and mid-band balance changes
along the existing stage chain, at matched presentation level. It also renders
level-matched excerpt pairs so the operator can listen. It does not decide that
any stage, profile, EQ, or master is better. It does not adopt a default, change
the accepted master, or claim to recover room/amp response.

In scope: one experimental helper `scripts/tone_ab.py` that reads an existing
run's stage files. It writes a fresh `tone-ab.json`, one reversible low-shelf
trial render, and three excerpt pairs under
`artifacts/s2/tone_ab/<run_id>-<UTCstamp>/`. Also in scope: tests, a skill
draft, and a typed tool-descriptor draft handed to root.

Out of scope: re-running denoise/EQ/compression/normalization on the whole take,
new profile schema, forwarding the shelf to tool25/`apply_capture_profile`,
listening acceptance, AU work, Linear writes, and model downloads. Pitch, note,
or missed-note claims are also out of scope.

## Owned files

| File | Role |
| --- | --- |
| `scripts/tone_ab.py` | Helper/CLI (`run`, `describe`); stdlib + FFmpeg/FFprobe only |
| `tests/test_tone_ab.py` | ≥10 tests; FFmpeg-dependent tests `skipUnless` FFmpeg resolves |
| `docs/spec/sprints/TONE_S2.md` | This contract and preregistration |
| `.agents/skills/guitar-tone-ab/SKILL.md` | Skill draft. Root admits it. |
| `docs/agent-notes/sprints/20261006-s2/tone_ab-*.json` / `tone_ab-*.md` | Run/implementation receipts |

Root-owned changes (descriptor in `program/tools.json`, MCP/tool_api wiring,
`just` recipe) are requested only through `root_owned_changes_requested`.

## Inputs and arms

CLI: `python3 scripts/tone_ab.py run --run-dir D [--candidate-run-dir C]
--common-region-start S --common-region-end E [--timeout-seconds T]`.

The actual run is `run_dir = /Users/jess/git/video-utils/artifacts/runs/20261006T041633Z-990aa1bd6737`
(accepted FULLER, read-only), with S = 5.0 and E = 150.0. Native PCM is 44100 Hz
mono, 6,657,385 frames.

| Arm label | File | Stage meaning |
| --- | --- | --- |
| `source` | `source.wav` | Decoded native source PCM |
| `pure_denoise` | `denoised.wav` | afftdn NR8 captured-profile output, latency-compensated |
| `tone_dynamics_pre_gain` | `processed.wav` | FULLER EQ (160 Hz +2, 300 Hz +1) and compressor, combined. These cannot be separated here. |
| `delivery_master` | `cleaned.wav` | Accepted FULLER delivery PCM after loudness normalization. The mode is copied from the manifest. |
| `trial_lowshelf` | rendered | Reversible experiment derived from `delivery_master` (see preregistration) |
| `candidate_*` (optional) | candidate run's `denoised.wav`/`processed.wav`/`cleaned.wav` | Same checks; flagged `denoise_basis_differs_confounded` if its denoised sha256 ≠ the run's |

`source`, `pure_denoise` and `delivery_master` are required. `tone_dynamics_pre_gain`
is used when the manifest lists it. If it is absent, the record says `absent` and
gives a reason.

Per-arm identity gate (refusal before any output directory is published):

1. The file sha256 (streamed) equals `manifest.output_sha256[<name>]`.
   Otherwise refuse with `stage_hash_mismatch`.
2. Native extent is read from the RIFF header by a stdlib parser (format tag
   1/3/0xFFFE, rate, channels, bits, data frames). It must equal `manifest.pcm`
   rate/channels/sample_count. FFprobe cross-checks when available. A mismatch
   refuses with `native_extent_mismatch`.
3. A candidate run must share `manifest.source.sha256`. Otherwise refuse with
   `candidate_source_mismatch`.

## Common region and closed input schema

`common_region_start` and `common_region_end` are explicit native-source seconds.
They are finite numbers, never booleans. Refuse if start < 5.0 (the 0–5 s setup
guitar/amp and windup interval is never measured). Refuse if end ≤ start, if end
exceeds the run duration, or if end − start < 45.0 (the three 15 s excerpts must
fit without overlap). Sample bounds are `round(s × rate)`, and the end is
exclusive. `timeout_seconds` is an integer from 1 to 1800 (default 1200). Unknown
fields, a nonexistent run_dir, and a run_dir without `manifest.json` are refused.

The output directory must be fresh. Refuse if it exists. Refuse if it resolves
inside `run_dir`, `candidate_run_dir`, or any `artifacts/runs/*` directory.
Work happens in a staging directory that is renamed into place on success. On
failure, only `tone-ab.failed.json` is kept, with the reason. All run-dir inputs
are opened read-only.

## Measurements (claim class M unless marked)

All arms are decoded for the common region by FFmpeg (`atrim=start_sample:end_sample`,
`-f f32le` to stdout, sample-exact, no resampling). Each subprocess timeout is
min(120 s, remaining deadline). One process runs, with at most one FFmpeg child
at a time.

1. **Loudness and match.** Integrated LUFS per arm over the region uses FFmpeg
   `loudnorm=print_format=json` `input_i` (BS.1770 gating), the same meter as
   `media.loudness`. The target is the minimum region LUFS across all measured
   arms, so every static gain is ≤ 0 dB and the match adds no clipping. Gain is
   `target − measured`. LUFS is re-measured with `volume=<g>dB:precision=double`.
   If the result is still off by more than 0.3 LU, gain is corrected up to 3
   iterations. `match_lu_delta = max_arm |after − target|`. `match_status` is
   `matched` if `match_lu_delta ≤ 0.3`. Otherwise it is `unmatched` with a
   reason, and the remaining measurements are still reported but flagged. Each
   arm gets one gain for the whole region. There is no per-phrase normalization.
2. **Band energies.** Bands are 20–45, 45–90, 90–160, 160–400, 400–2000 and
   2000–8000 Hz. The method is Welch at native rate, frame N=16384 (2.69 Hz bins
   at 44.1 kHz), periodic Hann, hop N, and only frames fully inside the region.
   Band power is `2·Σ_{k: lo≤f_k<hi}|X_k|² / (N·Σw²)`, averaged over frames, so
   a sine of amplitude A reads A²/2. For each arm and band the report gives:
   `level_dbfs_raw`, `level_dbfs_matched` (= raw + gain_db, derived exactly for
   linear gain), `share_db` (the band relative to the six-band sum), `bin_count`
   and `frame_count`. A band reaching or above Nyquist is null with
   `above_nyquist`.
3. **Stage deltas.** Matched and raw per-band differences:
   `pure_denoise − source` (denoise stage), `tone_dynamics_pre_gain − pure_denoise`
   (EQ+compressor, combined), `delivery_master − tone_dynamics_pre_gain`
   (delivery normalization), `delivery_master − source` (end-to-end),
   `trial_lowshelf − delivery_master` (trial). These are mixture-energy changes.
   They do not separate fan from music (fan_only_gain and music_only_gain stay
   null).
4. **Attack panels.** Positions come from the analysis that is hash-bound to
   this run's `pure_denoise` sha256. The helper searches `run_dir/analysis.json`
   first, then the parent run's `analysis.json` derived from
   `manifest.capture_profile_application.authoring_dir`. It is accepted only if
   `source_lineage.analyzed_input_sha256` equals the run's denoised sha256 and
   the native rate/count match. Otherwise attack metrics are null with
   `no_hash_bound_attack_analysis`.
   Primary panel: `click_grid.observed_events` (identity
   `periodic_high_frequency_transients_not_verified_metronome`; may be clicks
   or picks). Secondary panel: `superflux_attack_candidate` events. For a
   position t, n0 = round(t·rate) and the window is [n0, n0 + round(0.020·rate)).
   Only windows fully inside the region count. Per arm: attack energy dBFS
   (10·log10 mean square; raw and matched) and spectral centroid Hz. The
   centroid is computed with a Hann window over the 20 ms window, zero-padded to
   the next power of two, over bins 20 Hz..min(20 kHz, Nyquist), and is null on
   zero energy. Per-panel denominators: events in analysis, in region, and used.
   Summary per arm: median and IQR energy, median centroid, and paired
   per-position median deltas versus `source` and `pure_denoise`. Timestamp
   uncertainty (±5 ms analysis hop, uncalibrated detector delay) is recorded.
5. **Excerpt pairs (for listening, class L pending).** Placement is fixed by
   rule: center_i = S + (E−S)·(2i+1)/6 for i=0,1,2, with window
   [center−7.5, center+7.5] s. Each pair is `source` versus `delivery_master`,
   with the region's static gains applied, written as native-rate/channel f32
   WAV of exactly round(15·rate) frames (661,500 at 44.1 kHz). Labels X/Y are
   assigned by `random.Random(20261006 + i)`, and the key is stored in
   `tone-ab.json` (the operator should listen before reading it). For each file
   the report gives sample peak dBFS, excerpt LUFS (informational; not
   re-matched) and sha256. True peak is null unless measured.
6. **Protected readback.** Before and after the run, the helper records sha256,
   size and mtime for every regular file in `run_dir` (and `candidate_run_dir`).
   Any change makes the status `protected_input_changed`. That is a failure.

For the actual run, the pure-denoise→processed→master stage chain uses existing
files. Only the trial arm and the excerpts are newly rendered.

## Preregistered experiment (sealed by this commit)

- **Arm (exactly one):** `trial_lowshelf`. The FFmpeg filter is
  `lowshelf=f=100:t=q:w=0.7:g=1.5:r=f64`, applied to `delivery_master`
  (`cleaned.wav`) over the full native extent, written as f32 so it cannot clip.
  It must have the same rate/channels/frame count. It is reversible: the accepted
  master is untouched, and the trial is a separate deletable file with recorded
  sha256 and filter string. Root decides whether to keep it.
- **Fixed before truth:** shelf parameters, bands, Welch/attack parameters,
  region S=5.0/E=150.0 for the actual run, excerpt rule, blind seed 20261006,
  and the 0.3 LU tolerance. None of these is changed after seeing results. No
  second shelf, gain, frequency, or region is tried. There is no held-out set
  (single take). Synthetic test fixtures only verify mechanics and are never
  used to select parameters.
- **Scoring/recording:** report `trial_lowshelf − delivery_master` for all six
  bands (raw and matched), attack deltas, and `delta_20_45_db` {raw, matched}.
  Expectation from filter theory (inference, not measurement): about +1.3 to
  +1.5 dB raw at 20–45 Hz, smaller after the loudness match. Status is always
  `rejected_or_unreviewed_trial`, `adopted: false`,
  `forwarded_to_profile: false`, whatever the numbers show.
- **eq_floor_change_proposed:** `{current_schema_min_hz: 160, trial_shelf_hz: 100,
  measured_delta_20_45_db: {raw, matched}, decision: "root_and_operator_review_required",
  adopted: false}`. A measured increase is not evidence of fuller perceived tone,
  a recovered fundamental, or room response.
- **Non-improvement is a valid completion.** If the match fails or the trial
  barely moves 20–45 Hz, that result is recorded as is.

## Required explicit unknown/abstain fields in `tone-ab.json`

`operator_preference: null`, `listening_accepted: false`,
`room_response_recovered: false`, `perceived_fullness: null`,
`nasal_quality: null`, `fan_only_gain: null`, `music_only_gain: null`,
`fundamental_32hz_presence: null` (a band level is mixture energy, not a measured
played C1), `capture_chain_response: null`, `monitoring_device: null`,
`attack_identity: "unverified"`, `true_peak_dbtp: null` unless measured,
`stage_separation_eq_vs_compressor: "not_separable_combined_stage"`,
`default_adopted: false`, `master_changed: false`. Each null has a `reason`. A
`claims` object lists `measurements`, `inferences` and `listening` (empty until
the operator responds) separately.

## Completion metrics (denominators and claim classes)

| # | Metric | Denominator | Class |
| --- | --- | --- | --- |
| 1 | Stage files hash- and extent-verified against manifest | 4/4 actual stage files (+ candidate files if given); trial render extent equal 1/1 | M |
| 2 | `match_lu_delta ≤ 0.3` LU, else `unmatched` with reason | arms measured (5 for actual run) | M |
| 3 | Band cells reported raw+matched with bin/frame counts | 6 bands × 5 arms = 30 cells | M |
| 4 | Attack energy/centroid per arm for both panels | positions used / in region / total events (primary total 219 in the bound analysis) | M |
| 5 | Excerpt pairs rendered, exact 15 s native extent, shared static gains | 3/3 pairs (6 files) | M; preference L = pending |
| 6 | Exactly one experiment arm with `rejected_or_unreviewed_trial` and `delta_20_45_db` | 1/1 | M + I |
| 7 | Accepted run dir unchanged (sha256/size/mtime) | n/n files in run_dir | M |
| 8 | Unknown/abstain fields present with reasons | 15/15 listed fields | contract |
| 9 | `tests/test_tone_ab.py` passing; skipped-with-reason count reported | ≥10 tests | M |
| 10 | Descriptor + skill drafts handed to root | 2/2 | contract |

Listening outcomes, perceived fullness, and nasal quality stay operator-owned.
Numbers alone never close the operator's thin/nasal feedback.

## Test protocol

Run from the worktree root with
`PYTHONPATH=tests python3 -m unittest test_tone_ab -v` (FFMPEG/FFPROBE exported
per lane rules). Only `test_tone_ab` and directly affected modules are run. The
synthetic fixtures are stdlib-generated f32 WAVs in a temporary directory with
fake `manifest.json`/`analysis.json`. Synthetic runs use 22050 Hz mono and 55 s
so they stay small. Planned tests:

1. `test_schema_rejects_unknown_fields_bool_nonfinite`: closed schema, boolean-as-number, NaN/inf, wrong types.
2. `test_region_bounds_refusal`: start < 5.0, end ≤ start, end > duration, length < 45 s.
3. `test_timeout_bounds`: 0, 1801, non-integer refused; 1 and 1800 accepted.
4. `test_stage_hash_mismatch_refusal`: one byte changed in `denoised.wav` → `stage_hash_mismatch`, and no output dir is published.
5. `test_native_extent_mismatch_refusal`: a manifest frame count off by one → refusal.
6. `test_no_master_overwrite_and_protected_readback`: an output inside run_dir or `artifacts/runs/*` is refused. After a successful synthetic run, every run_dir file has an unchanged sha256/size/mtime.
7. `test_fresh_output_dir_required`: an existing destination is refused.
8. `test_gain_iteration_converges_with_fake_meter`: pure logic, ≤ 3 iterations, all gains ≤ 0.
9. `test_band_energy_sine_calibration`: a 32.703 Hz sine at A=0.5 reads −9.03 ± 0.2 dB in 20–45 and is ≥ 30 dB below in 400–2000. A 1 kHz sine lands in 400–2000.
10. `test_two_tone_match_convergence_ffmpeg` (FFmpeg): two arms with different 32.7 Hz/1 kHz mixes and levels converge to `match_lu_delta ≤ 0.3`.
11. `test_excerpt_extent_preservation_ffmpeg`: 3 pairs, each exactly round(15·rate) frames, at native rate/channels, using the rule placement and seeded labels.
12. `test_attack_analysis_hash_binding`: a mismatched `analyzed_input_sha256` gives null attack metrics with a reason. A bound analysis gives correct denominators and window extents.
13. `test_trial_arm_fields_and_reversibility_ffmpeg`: exactly one trial arm, the exact status string, `operator_preference` null, `room_response_recovered` false, and `eq_floor_change_proposed` carrying the measured delta with `adopted: false`. A g=0 shelf is a near-null identity within 1e-4 RMS.
14. `test_centroid_gain_invariant_and_unknown_fields_present`.
15. `test_descriptor_draft_closed_schema`: the draft descriptor has exactly the inputs run_dir, candidate_run_dir, common_region_start, common_region_end, timeout_seconds, with `additionalProperties: false`.

## Execution bounds and receipts

There is one heavy job at a time, with an overall monotonic deadline of
`timeout_seconds`. The helper starts no daemons and writes nothing to accepted
run dirs, Documents/Desktop, or `.local/sprint1`. Phase 2 executes once on the
actual run and records a dated receipt at
`docs/agent-notes/sprints/20261006-s2/tone_ab-<stamp>.json` and `.md`. The
receipt includes script sha256, spec commit, input hashes, metrics against the
denominators above, and the ruling citation.

Receipt: `tone_ab | spec only, no numerics | Phase 1 contract freeze and
preregistration | R-N13 (R-HOOK-CONVERGENCE-20261004) | accepted run
20261006T041633Z-990aa1bd6737 read-only | no default/profile/master adoption`.

## Phase 2 implementation notes (additive; preregistration above unchanged)

Implemented in `scripts/tone_ab.py` (first commit b8b3007). None of the sealed
parameters (shelf, bands, Welch/attack parameters, region 5.0–150.0 s, excerpt
rule, seed 20261006, 0.3 LU tolerance) changed. The following choices were left
open by the contract and are now fixed in code:

- **Paths.** `run_dir`/`candidate_run_dir` must be exact local directories, with
  no `..` and no symlink component. This matches the tool_api convention.
  Refusals before staging (schema, region, paths, `stage_hash_mismatch`,
  `native_extent_mismatch`, `candidate_source_mismatch`, `output_dir_exists`,
  `output_dir_protected`) write nothing. Failures after staging rename the
  staging directory to `<output>.failed/`, which holds only `tone-ab.failed.json`.
  `<output>` is never published on failure.
- **Gate order.** Cheap manifest checks (candidate source sha256, pcm) run
  before hashing. Stage sha256 values come from the protected-readback snapshot
  (streamed `media.sha256`), so each file is hashed once before measurement and
  once after.
- **CLI-only `--output-dir`.** It is not part of the tool schema. The same
  freshness and protection refusals apply. The default is
  `artifacts/s2/tone_ab/<run_id>-<UTCstamp>/`.
- **Levels.** All levels are dB re 1.0 mean square, so a full-scale sine reads
  −3.01 dBFS. With multiple channels, power is averaged across channels.
- **Attack centroid.** Periodic Hann over the 20 ms window, zero-padded to the
  next power of two. It is weighted by magnitude (librosa convention) over bins
  20 Hz..min(20 kHz, Nyquist).
- **Positions.** Attack positions use `audio_relative_seconds`, because the
  run's PCM sample 0 is the first decoded audio sample (`manifest.timeline`).
  Per-position rows are written to `attack-positions.json` (hash recorded in
  `tone-ab.json`).
- **Iteration.** `match_gains` re-measures every arm with
  `volume=<g>dB:precision=double`, including the 0 dB target arm. A correction
  that would make a gain positive is clamped to 0 and flagged.
- **FFT.** A stdlib recursive radix-2 FFT with a real-input packing step, with
  no numpy. Unit tests check it against a direct DFT.
- **Script hash.** `script_sha256` is captured at the start of a run, so it
  binds the code that actually executed.
- **Wall time.** On 2026-10-06 the host load average was about 200–390 on 6
  cores, because other lanes were running. Wall time in receipts reflects that
  contention, not the helper's intrinsic cost.

Root-owned registration (the `program/tools.json` descriptor from
`python3 scripts/tone_ab.py describe`, the `scripts/tool_api.py` worker branch,
a `just` recipe, and the S1 admission tool-count test) is requested through
`root_owned_changes_requested`, not edited here.

### Phase 2 integration hardening (additive; numerics unchanged)

- **Finalization reserve.** FFmpeg work stops `min(10 s, 5% of timeout_seconds)`
  before the overall deadline (`finalize_reserve`). That leaves time for the
  protected readback, `tone-ab.failed.json` and the rename before an outer
  supervisor can act. tool_api's process-group kill fires at exactly
  `timeout_seconds`. Total wall time stays ≤ `timeout_seconds`.
  `timing.finalize_reserve_seconds` records the value.
- **Descriptor draft file.** `docs/agent-notes/sprints/20261006-s2/tone_ab-tool-descriptor.json`
  is the exact `describe` output that root should append to `program/tools.json`.
  `test_descriptor_draft_closed_schema` asserts that the file equals
  `DESCRIPTOR_DRAFT`.
- The actual-run receipt (20261006T120702Z, script sha256 `ab900835…`) predates
  this change. The reserve does not touch any measurement path, and that run
  finished with 694 s of its deadline left, so its numbers stand.
