# tone_ab Phase 2: actual run receipt (2026-10-06T12:07:02Z)

`tone_ab | lane-owned helper | accepted FULLER run 20261006T041633Z-990aa1bd6737 read-only | completed, matched | R-N13 (R-HOOK-CONVERGENCE-20261004; TIN-3692 comment 98cf680c-7299-4949-bfb2-60079053ad43) | no default/profile/master adoption`

- Sprint 20261006-s2, Linear TIN-5601 (parent TIN-5599). The lane writes nothing to Linear.
- The contract is `docs/spec/sprints/TONE_S2.md`, frozen and preregistered at
  commit `9bc259d6cf964cab8498e4e90ae6ae27f85be3fc`.
- The run used script sha256 `ab900835c6e17253f6e6a3985bbae1d2e92b1352c7f47a695cbdcc6e1b3e6fa5`,
  committed as b8b3007. The later commit b8b64b5 adds only the run-dir symlink and
  traversal refusal. Numerics are unchanged.
- The output directory is gitignored and was not committed:
  `.local/sprint2/tone_ab/artifacts/s2/tone_ab/20261006T041633Z-990aa1bd6737-20261006T120702Z/`.
  `tone-ab.json` sha256 is `2736e3d39b218577a7c2753eff23a227032dc9544a57ad273d176125059ca8d4`.
- The structured companion is `tone_ab-20261006T120702Z-actual-run.json` in this
  folder. It distills the record and withholds the blind key.

## Invocation (preregistered values, unchanged)

`python3 scripts/tone_ab.py run --run-dir /Users/jess/git/video-utils/artifacts/runs/20261006T041633Z-990aa1bd6737 --common-region-start 5.0 --common-region-end 150.0 --timeout-seconds 1800`

- **Region:** native samples [220500, 6615000), which is 6,394,500 frames at
  44100 Hz mono. The 0–5 s setup interval was excluded.
- **Wall time:** 18 m 26 s, with 694 s of the deadline left and 32 bounded FFmpeg
  children. The host load average was about 90–390 on 6 cores because other
  lanes were running. Wall time therefore reflects contention.

## Measurements (class M)

| Metric | Result | Denominator |
| --- | --- | --- |
| 1 Stage files hash + native extent (RIFF and FFprobe) | 4 verified; trial extent equal | 4/4 stage files; trial 1/1 |
| 2 Loudness match | `match_lu_delta` 0.010 LU, `matched`, 0 corrections | 5/5 arms |
| 3 Band cells raw and matched | 30 | 30 (6 bands × 5 arms; 390 Welch frames each) |
| 4 Attack positions | primary 215 used / 215 in region / 219 events; secondary 482 / 482 / 495 | per panel |
| 5 Excerpt pairs at 661,500 frames, 44100 Hz, mono f32 | 3 pairs (6 files) | 3/3 |
| 6 Experiment arm `rejected_or_unreviewed_trial` | 1 | 1/1 |
| 7 Accepted run dir unchanged (sha256/size/mtime) | 13 | 13/13 files; analysis.json sha256 unchanged |
| 8 Unknown/abstain fields present with reasons | 15 | 15/15 |

**Region loudness.** These values are FFmpeg loudnorm `input_i` before matching.
Static gain matched every arm to the target of −21.33 LUFS (pure_denoise, the
quietest arm).

| Arm | LUFS | Gain | After |
| --- | --- | --- | --- |
| source | −21.16 | −0.17 | −21.33 |
| pure_denoise | −21.33 | 0.00 | −21.33 |
| tone_dynamics_pre_gain | −20.08 | −1.25 | −21.32 |
| delivery_master | −17.96 | −3.37 | −21.34 |
| trial_lowshelf | −17.81 | −3.52 | −21.33 |

**Band levels.** Values are matched dB re 1.0 mean square (Welch, N=16384).

| Arm | 20–45 | 45–90 | 90–160 | 160–400 | 400–2k | 2k–8k |
| --- | --- | --- | --- | --- | --- | --- |
| source | −57.32 | −38.80 | −26.95 | −23.88 | −31.96 | −30.48 |
| pure_denoise | −59.39 | −38.96 | −26.86 | −23.85 | −32.67 | −30.42 |
| tone_dynamics_pre_gain | −60.66 | −39.50 | −26.51 | −23.23 | −33.50 | −31.82 |
| delivery_master | −60.72 | −39.52 | −26.62 | −23.24 | −33.38 | −31.74 |
| trial_lowshelf | −59.42 | −38.59 | −26.31 | −23.31 | −33.53 | −31.89 |

**Stage deltas.** These are matched dB of mixture energy. Fan and music are not
separated.

| Stage | 20–45 | 45–90 | 90–160 | 160–400 | 400–2k | 2k–8k |
| --- | --- | --- | --- | --- | --- | --- |
| denoise (pure_denoise − source) | −2.07 | −0.16 | +0.09 | +0.03 | −0.71 | +0.07 |
| EQ+compressor combined (processed − pure_denoise) | −1.28 | −0.54 | +0.35 | +0.62 | −0.83 | −1.40 |
| delivery normalization (cleaned − processed) | −0.06 | −0.02 | −0.11 | −0.01 | +0.12 | +0.07 |
| end to end (cleaned − source) | −3.40 | −0.72 | +0.33 | +0.64 | −1.43 | −1.26 |
| trial (lowshelf − cleaned) | +1.31 | +0.93 | +0.32 | −0.07 | −0.15 | −0.15 |

Raw (unmatched) deltas:

- **End to end:** +3.84 dB at 160–400 Hz and −0.20 dB at 20–45 Hz.
- **Trial:** +1.46 dB at 20–45 Hz.

**Trial.** `lowshelf=f=100:t=q:w=0.7:g=1.5:r=f64` was applied to `cleaned.wav`.
The trial sha256 is `7d8637a0925b…` (full value in the JSON receipt). Results:

- `delta_20_45_db` was raw +1.457 and matched +1.307.
- The record keeps `status: rejected_or_unreviewed_trial`, `adopted: false` and
  `forwarded_to_profile: false`.
- `eq_floor_change_proposed` holds the 160 Hz schema floor, the 100 Hz trial
  shelf, the measured delta, `decision: root_and_operator_review_required` and
  `adopted: false`.

**Attack panels.** Positions come from the parent run 20261005T232741Z-2b5dc43fd009
`analysis.json`. It is bound by `analyzed_input_sha256` = denoised
`26c9f42c…`. Matched median paired deltas:

- **Primary (219 click-grid events):**
  - delivery_master vs source: −0.51 dB energy and −133 Hz centroid.
  - delivery_master vs pure_denoise: −0.48 dB and −173 Hz.
  - trial vs delivery_master: +0.01 dB and −19 Hz.
- **Secondary (superflux candidates):**
  - delivery_master vs source: −0.30 dB and −169 Hz.
  - trial vs delivery_master: +0.01 dB and −17 Hz.

## Inferences (class I, not measurements)

- At matched level the 20–45 Hz mixture share falls 3.40 dB from source to
  delivery master. About 2.07 dB of that falls at the denoise stage and 1.28 dB
  at the combined EQ+compressor stage. The EQ+compressor value is relative: the
  160/300 Hz boosts raise loudness, so the static match lowers everything else.
  This is consistent with the historical NR8 2.0–2.8 dB 20–45 Hz reduction. It
  is unknown how much of the removed 20–45 Hz energy was fan and how much was
  instrument.
- Energy at matched level moves toward 90–400 Hz and away from 400 Hz–8 kHz. A
  lower attack centroid (about −130 to −170 Hz) at the same positions goes with
  that shift. Whether this reads as "fuller", "thin" or "nasal" is a listening
  question. These numbers do not answer it.
- The trial behaved as filter theory predicted: about +1.3 to +1.5 dB at
  20–45 Hz, slightly smaller after matching, with spill into 45–160 Hz. It does
  not restore the 3.40 dB end-to-end matched 20–45 Hz loss.

## Listening (class L)

None yet. Six blind excerpt files (`excerpt-{1,2,3}-{X,Y}.wav`, source versus
delivery master at the region's static gains) wait for the operator. The X/Y key
is only in `tone-ab.json` `excerpts.blind_key`; listen before opening it. The
following stay unresolved:

- `operator_preference`, `perceived_fullness`, `nasal_quality`,
  `capture_chain_response` and `monitoring_device` are null.
- `listening_accepted` and `room_response_recovered` are false.
- `fundamental_32hz_presence` is null, because a band level is not a played C1.
- `attack_identity` is unverified.

## Boundaries kept

- The accepted run dir was read only, and readback found 13/13 files unchanged.
- No master, profile, default or detector was adopted.
- There was no Linear write, no model download and no daemon.
- No write touched `artifacts/runs/*`, Documents, Desktop or `.local/sprint1`.
- Root owns registration (descriptor, tool_api branch, `just` recipe, admission
  tool count). Those changes are requested through the lane return, not edited.
