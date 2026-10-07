# S2R lane eq_shelf: bounded, reversible low-shelf below 160 Hz

Sprint 20261007-s2r, Linear TIN-5487. Lane branch `sprint/20261007-s2r/eq_shelf`,
worktree `.local/sprint2/eq_shelf`, baseline commit `7d0e11e`. Authority: the
operator ruling of 2026-10-07 ("EQ below 160 Hz: allow a bounded shelf below
160 Hz"), recorded by root in
`docs/agent-notes/2026-10-07-s2-operator-rulings.md` (main checkout, sha256
`62b92262…6bb85` at freeze); repository AGENTS.md; R-HOOK-CONVERGENCE-20261004
(R-N11/R-N12/R-N13). This is the Phase 1 contract freeze. No numerics ran
before this commit, which seals the preregistration in section 7.

The lane never pushes, merges, writes Linear, changes the default profile,
adopts a master, edits the accepted run or touches Desktop/Documents. Root
signs and integrates.

## 1. Ruling and scope

The ruling text is: "Capped, reversible low-shelf as an explicit profile
option; default FULLER unchanged; never a cut or notch near the ~32 Hz
fundamental."

In scope:

1. **`scripts/media.py`**: one new optional profile control, `low_shelf`. It
   is validated in `validate_post_controls` and rendered by
   `post_denoise_filters` as a single FFmpeg `lowshelf` biquad. The bounds
   below are enforced with typed `MediaError.code` reasons. There are two new
   optional status keys, `operator_review_status` and `listening_acceptance`.
   They are required whenever `low_shelf` is present.
2. **`profiles/fuller-shelf.json`** (new, optional): FULLER-v1 controls copied
   verbatim from `profiles/fuller.json`, plus
   `low_shelf {frequency_hz 100.0, gain_db 1.5, q 0.7}`. This is the trial
   measured by tone_ab. The profile is marked `operator_review_status:
   "unreviewed_trial"` and `listening_acceptance: "not_performed"`.
3. **Tests** in `tests/test_eq_shelf.py` (new). `tests/test_media.py` is
   touched only if an existing assertion must follow the new closed key set.
   The plan is to leave it unchanged.
4. **Skill text**: `.agents/skills/guitar-denoise/SKILL.md` documents the
   knob, its bounds, reversibility, and that preference requires listening.
5. **Receipts**: `docs/agent-notes/sprints/20261007-s2r/eq_shelf-*.json`.

Out of scope: changing `profiles/fuller.json` (it must stay byte-identical),
`DEFAULT_PROFILE` (stays `"fuller"`), peaking-EQ bounds (stay 160–6000 Hz,
±3 dB, Q 0.5–2), and high-pass, notch, high-shelf or cut controls of any kind.
Also out of scope: MCP/tool descriptor registration (root-owned; see section
9), re-rendering or replacing the accepted run or any Desktop export, listening
acceptance, and any claim that the shelf restores an uncaptured fundamental or
the in-room amp tone.

## 2. Inputs read (read-only, hashes at freeze)

| Item | Identity |
| --- | --- |
| `scripts/media.py` (baseline) | `4a6289ad…4f466bc2` |
| `profiles/fuller.json` (must stay unchanged) | `33da74c7d1bda246b6349252e4374d3674e76356dd85d72a83b1389988d04a5c` |
| tone_ab actual-run receipt | `docs/agent-notes/sprints/20261006-s2/tone_ab-20261006T120702Z-actual-run.json`, `328717ea…e8ce9ef6` |
| `.agents/skills/guitar-denoise/SKILL.md` (baseline) | `1a83c20d…a87c68` |
| `tests/test_media.py` (baseline) | `d83397da…a8062` |
| Accepted FULLER run | `artifacts/runs/20261006T041633Z-990aa1bd6737` (main checkout, never written) |
| FFmpeg | 8.1.2 at `/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin` via `FFMPEG`/`FFPROBE` env |

**Prior measurement (tone_ab, measured, real take, matched level).** The trial
filter `lowshelf=f=100:t=q:w=0.7:g=1.5:r=f64` raised the 20–45 Hz band by
+1.307 dB matched (+1.457 dB raw) over 390 frames and 9 bins. That trial was
applied **after** delivery loudness normalization (`delivery_master`). In this
lane the shelf sits **before** compression and loudness normalization (section
3.3), so the tone_ab delta does not transfer to a FULLER-shelf render. That
transfer is recorded as `real_take_effect_in_chain: "unknown"` unless the
optional E3 arm runs. tone_ab's own label for the trial was
`rejected_or_unreviewed_trial`. Its listening acceptance was not performed.

## 3. Contract

### 3.1 Control schema

`low_shelf` is an optional top-level profile key. Its value is a **single
JSON object** with exactly the keys `{frequency_hz, gain_db, q}`. Each value
is a finite JSON number. Booleans and strings are refused.

| Field | Bound (inclusive) | Rationale |
| --- | --- | --- |
| `frequency_hz` | 80 … 160 | Ruling: a shelf below 160 Hz. 80 Hz is the floor, so the corner never approaches the 32.7 Hz C1 string. |
| `gain_db` | 0.0 … +2.0 | Boost only, per the ruling cap. Any negative value, including `-0.0` (sign bit set), is a cut and is refused. |
| `q` | 0.5 … 0.707 | With FFmpeg `t=q`, the RBJ cookbook shelf is monotonic (no overshoot dip) for Q ≤ 1/√2 (0.70711). This guarantees that a boost never yields a cut at any frequency. The trial's 0.7 lies inside. |

There is at most one shelf per profile. A list value, of any length, is
refused. A duplicated `low_shelf` key in a profile file is also refused (the
loader checks duplicate keys for `low_shelf` only; general duplicate-key
hardening is a follow-up, not this lane). Shelf-like objects inside
`peaking_eq` remain refused by the unchanged peaking schema (exact keys,
160–6000 Hz).

`operator_review_status` must be one of `{"unreviewed_trial"}`.
`listening_acceptance` must be one of `{"not_performed"}`. Both are optional
for profiles without `low_shelf` and **required** for profiles with it.
Widening either enum (for example, after operator listening) is an operator
decision that root applies. The lane cannot assign it.

### 3.2 Typed refusal reasons (`MediaError.code`)

| Code | Condition |
| --- | --- |
| `low_shelf_invalid` | Not an object; the key set is not exactly `{frequency_hz, gain_db, q}`; a value is boolean, non-numeric or non-finite |
| `low_shelf_multiple` | Value is a list (any length), or the `low_shelf` key appears more than once in the file |
| `low_shelf_frequency_out_of_bounds` | `frequency_hz` < 80 or > 160 |
| `low_shelf_cut_refused` | `gain_db` < 0 or is `-0.0` |
| `low_shelf_gain_out_of_bounds` | `gain_db` > 2.0 |
| `low_shelf_q_out_of_bounds` | `q` < 0.5 or > 0.707 |
| `low_shelf_review_status_required` | `low_shelf` present without both status keys |
| `low_shelf_review_status_invalid` | A status key is present with a value outside its enum |
| `low_shelf_above_nyquist` | `frequency_hz` ≥ sample_rate / 2 at render (unreachable at real rates; kept for parity with peaking EQ) |

All shelf refusals happen in `validate_profile`/`validate_post_controls`, so
`clean` refuses before source hashing, decode or run-directory creation, just
as invalid peaking EQ already does. The existing message and code behaviour
for all non-shelf errors is unchanged. In particular, `capture_interval_required`
for `fuller` is unchanged and also applies to `fuller-shelf`, because it
carries `noise_capture_required: true`.

### 3.3 Rendering

- Stage order in `post_denoise_filters` is `low_shelf` (when present), then
  `peaking_eq_1..n`, then `rms_compressor`. EQ runs before dynamics, as in the
  existing chain. Loudness normalization remains a separate later stage.
- Filter text: `lowshelf=f={f:.9g}:t=q:w={q:.9g}:g={g:.9g}:r=f64`. For the
  trial values this is exactly `lowshelf=f=100:t=q:w=0.7:g=1.5:r=f64`, which is
  byte-identical to tone_ab `experiment.filter`.
- Stage record: `{"stage": "low_shelf", "controls": {...}, "filter": "...",
  "timing": {"sample_axis_policy": "causal forward IIR; no block delay or time
  stretch", "frequency_dependent_phase": true, "acoustic_alignment_verified":
  false}, "boost_only": true, "reversibility": "procedural: re-render the
  unchanged source with profile fuller; the shelf is not inverted from a
  rendered master", "recreates_uncaptured_fundamental": false}`.
- Profiles without `low_shelf` produce stage lists and filter strings that are
  **byte-identical** to the baseline. For FULLER, P is
  `equalizer=f=160:t=q:w=0.7:g=2:b=0:r=f64,equalizer=f=300:t=q:w=0.8:g=1:b=0:r=f64,acompressor=threshold=0.125892541179:ratio=2:attack=15:release=100:knee=1.41253754462:makeup=1:level_in=1:mode=downward:link=maximum:detection=rms:mix=0.25`.
- FULLER-shelf P′ is `lowshelf=f=100:t=q:w=0.7:g=1.5:r=f64,` + P.

### 3.4 profiles/fuller-shelf.json

`name: "fuller-shelf"`. Every FULLER control key and value matches `fuller.json`
with the same JSON numeric types. That covers `noise_capture_required: true`,
the peaking EQ, the compressor and the loudness targets. On top of that it
adds `low_shelf`, `operator_review_status: "unreviewed_trial"` and
`listening_acceptance: "not_performed"`. The description states:

- The profile is an explicit, optional trial.
- It is not the default.
- It is not covered by the FULLER listening acceptance.
- The shelf sits before compression and loudnorm, unlike the tone_ab trial.
- Preference requires operator listening at matched level.
- It makes no claim of 32 Hz restoration, room or amp tone, or suitability on
  other takes.

## 4. Owned files

- `scripts/media.py`
- `profiles/fuller-shelf.json`
- `tests/test_media.py` (expected unchanged)
- `tests/test_eq_shelf.py`
- `docs/spec/sprints/EQ_SHELF_S2R.md` (this file)
- `.agents/skills/guitar-denoise/SKILL.md`
- `docs/agent-notes/sprints/20261007-s2r/eq_shelf-*.json`

Runtime outputs go only under `.local/sprint2/eq_shelf/artifacts/s2/eq_shelf/`
(gitignored). The lane reads `artifacts/runs/*` and `artifacts/experiments/*`
and never writes them.

## 5. Test protocol

Run from the worktree root with
`FFMPEG=…/ffmpeg FFPROBE=…/ffprobe PYTHONPATH=tests python3 -m unittest <module> -v`.
Run one module at a time; the FFmpeg tests use explicit `timeout` (≤ 120 s per
render).

| Module | Purpose |
| --- | --- |
| `test_eq_shelf` (new) | All shelf contract and fixture tests below. FFmpeg tests are `skipUnless` FFmpeg resolves; a skip is reported as a skip, not a pass. |
| `test_media` | Regression: must pass unchanged |
| `test_fuller_profile` | Regression: FULLER template identity, default and refusal |
| `test_capture_profile`, `test_apply_capture_profile` | Regression: they import `media.post_denoise_filters`/`load_profile` |
| `test_mcp` | Regression: the `guitar-denoise` prompt returns the edited skill text verbatim |

`test_eq_shelf` cases:

1. **Refusals (typed codes)**:
   - 79 Hz → `frequency_out_of_bounds`
   - 161 Hz → `frequency_out_of_bounds`
   - +2.1 dB → `gain_out_of_bounds`
   - −0.1, −2.0 and −0.0 dB → `cut_refused`
   - Two shelves as a list → `multiple`
   - A duplicated `low_shelf` key in a profile file → `multiple`
   - Q 0.49 and 0.71 → `q_out_of_bounds`
   - A boolean value, NaN, +inf, a missing key, an extra key (`type`) and a
     string value → `invalid`
   - Shelf without status keys → `review_status_required`
   - `listening_acceptance: "accepted"` → `review_status_invalid`

   That is 18 refusal cases, and each asserts the exact `code`.
2. **Accepted edges**: 80 Hz, 160 Hz, 0.0 dB, 2.0 dB, Q 0.5 and Q 0.707 each
   validate (6 cases).
3. **Peaking EQ unchanged**: 159 and 6001 Hz refused; 160 and 6000 Hz accepted
   (4 cases). A `peaking_eq` band at 100 Hz is still refused.
4. **FULLER identity**: sha256 of `profiles/fuller.json` equals `33da74c7…`;
   `media.DEFAULT_PROFILE == "fuller"`; the `post_denoise_filters` join for
   fuller equals P byte for byte; no fuller stage is named `low_shelf`.
5. **All existing profiles** (`bypass`, `captured12`, `captured8-clarity`,
   `captured8`, `conservative3`, `fuller`, `mild6`) load. Their post-denoise
   stage lists are unchanged against a baseline built from the frozen
   `media.py` source copy at `7d0e11e` (via `git show`) loaded in-process.
6. **FULLER-shelf filter**: the joined filter equals P′. The shelf stage filter
   equals the tone_ab receipt `experiment.filter`. The status keys equal
   `unreviewed_trial` and `not_performed`. Control keys other than the added
   three equal `fuller.json`.
7. **Default refusal unchanged**: `clean(<fixture>, "fuller")` and
   `clean(<fixture>, "fuller-shelf")` with no interval each raise
   `capture_interval_required`, with `media.sha256` and `media.probe` mocked
   and asserted not called. No `artifacts/runs` entry is created.
8. **Synthetic C1 fixture (FFmpeg; see section 7)**: the C1 delta is in
   (0, +2.0] dB. No component falls by more than 0.02 dB in the shelf-only arm.
9. **Skill text**: the skill names `low_shelf`, the bounds `80`–`160` Hz,
   `0`–`+2` dB, Q `0.5`–`0.707`, "boost only", "reversible", and "listening",
   and states that `fuller` remains the default (string checks).

## 6. Completion metrics (denominators and claim classes)

Claim classes: **C** contract/code behaviour, **M** measurement on a synthetic
fixture, **I** inference from filter theory, **L** listening (not performed by
this lane).

| # | Metric | Denominator | Class |
| --- | --- | --- | --- |
| 1 | Shelf refusals with the exact typed code | x/18 | C |
| 2 | Accepted edge cases validate | x/6 | C |
| 3 | Peaking-EQ bound checks unchanged | x/4 (+1 sub-160 band refused) | C |
| 4 | FULLER unchanged: file hash, default name, P byte equality | x/3 | C |
| 5 | Existing profiles load with byte-identical stage lists | x/7 | C |
| 6 | FULLER-shelf P′ equality and shelf filter == tone_ab trial filter | x/2 | C |
| 7 | `capture_interval_required` before hashing/decode for fuller and fuller-shelf | x/2 | C |
| 8 | C1 (32.703 Hz) delta, shelf-only arm, in dB, reported to 0.001 dB with pass band (0, +2.0] | 1 component / 1 fixture | M |
| 9 | Components not cut (Δ ≥ −0.02 dB), shelf-only arm | x/9 components | M |
| 10 | Measured C1 delta vs RBJ analytic magnitude at 32.703 Hz (report, ±0.15 dB agreement band) | 1/1 | M vs I |
| 11 | Full post-chain arm (P′ vs P) C1 delta and per-component deltas | report only, 9 components | M |
| 12 | Skill text checks | x/8 strings | C |
| 13 | Regression modules pass | tests passed / run (skips listed separately) per module | C |
| 14 | Listening preference | `not_performed` | L |

Completion means metrics 1–9, 12 and 13 at full denominator, with 10 and 11
reported. If metric 10 falls outside its band, that is a reported finding about
FFmpeg versus the textbook formula. It does not trigger tuning. An experimental
non-improvement (for example, metric 11 showing the compressor offsets part of
the boost) is a valid completion and is reported as measured.

## 7. Preregistration (sealed by this commit)

- **Parameters are fixed.** The shelf is f=100.0 Hz, gain=+1.5 dB, Q=0.7,
  taken from the tone_ab receipt before any lane numerics. No parameter search,
  no sweep and no re-selection after seeing results. The bounds come from the
  ruling and the monotonicity argument, not from data.
- **Fixture F1 (deterministic, no seed):** 44,100 Hz mono float32, 8.0 s.
  The signal is the sum of k·32.703 Hz for k = 1..9 with amplitudes
  a_k = 0.25/k and phase 0. The peak is bounded below 0 dBFS; the test
  asserts the peak before rendering. A 50 ms raised-cosine fade-in and
  fade-out is applied. The C1 frequency 32.703 Hz is the theoretical A4=440
  equal-temperament C1 from `program/instrument.json`. It is not a measured
  string pitch. Components above C1 are a synthetic harmonic series, not a
  model of the instrument.
- **Arms.**
  - E1 shelf-only: F1 → `lowshelf=f=100:t=q:w=0.7:g=1.5:r=f64`.
  - E0 identity: F1 → `anull`, which is the reference.
  - E2 full post chain: F1 → P′ versus F1 → P. Report only; this arm includes
    the compressor and has no loudnorm.
  - All arms run through FFmpeg 8.1.2, `-threads 2`, output f32le, with a
    120 s timeout each.
- **Scoring.** Analysis window [2.0 s, 6.0 s), past the IIR transient and
  fades. For each k, estimate amplitude by least-squares projection onto
  sin/cos at k·32.703 Hz over the window. Δ_k = 20·log10(A_arm/A_ref) dB, with
  the denominator stated per component. E1 passes if 0 < Δ_1 ≤ 2.0 and
  Δ_k ≥ −0.02 dB for all k (9/9). The RBJ analytic |H(32.703 Hz)| is computed
  from the cookbook formulas with the same f, Q, gain and rate (class I) and
  reported beside Δ_1.
- **Expectation (inference, not measurement).** Δ_1 is between about +1.2 and
  +1.5 dB. Harmonics at or above 5 × 32.703 Hz are near +0.1 dB or less. Δ_1
  in E2 is positive but may be smaller than in E1 because of compressor
  interaction.
- **Truth before scoring.** F1 is generated by code committed before any
  render. No held-out set exists, and no knob is tuned on any output.
- **Optional E3 (real-take audition pair, report only, may be skipped).**
  - Input: the accepted run's `denoised.wav` (read-only, hash recorded),
    excerpt 5.0–35.0 s.
  - Render P and P′.
  - Loudness-match both to −18 LUFS using integrated loudness from FFmpeg
    `ebur128`. The match must be within 0.1 LU, with gain correction only.
  - Report 20–45, 45–90 and 90–160 Hz band energy deltas (matched and raw,
    with frame/bin counts) and write the pair to `artifacts/s2/eq_shelf/`.
  - This arm makes no preference claim. It is not a master and does not
    change the accepted run.
  - Skipping E3 leaves `real_take_effect_in_chain: "unknown"`.

## 8. Unknown and abstain fields the outputs must carry

`profiles/fuller-shelf.json` carries `operator_review_status:
"unreviewed_trial"` and `listening_acceptance: "not_performed"`.

The lane run receipt (`eq_shelf-<UTC>-run.json`) carries, explicitly:

- `listening_preference: null` with `listening_status: "not_performed"`
- `real_take_effect_in_chain: "unknown"`, or the E3 measurements with their
  scope
- `isolated_guitar_spectrum: "unknown"`
- `microphone_low_frequency_response: "unknown"`
- `c1_presence_in_take: "not_established"`. The fixture frequency is
  theoretical, and no claim is made that C1 was played or captured.
- `fan_noise_overlap_below_160_hz: "unknown"`
- `recreates_uncaptured_fundamental: false`
- `default_profile_changed: false`
- `accepted_run_modified: false`
- `fuller_json_sha256` (before/after)
- FFmpeg version string, the hashes of code and profile used, and the test
  pass/run/skip counts per module

## 9. Root-owned changes requested (lane does not apply)

- **`program/tools.json` / `scripts/tool_api.py`**: optional registration of
  `fuller-shelf` as a selectable profile for MCP `denoise`, with descriptor
  text saying it is an unreviewed trial that needs a capture interval. The
  current frozen descriptor does not accept `fuller` either, so this follows
  that root decision.
- **`scripts/report.py`** (not lane-owned): a delivery-chain label for stage
  `low_shelf` ("low shelf {f} Hz / +{g} dB / Q {q}, boost only"). Also include
  `low_shelf` in the `analysis_stage_caption` post-stage predicate. Without
  this, the generic fallback label "low shelf" is shown without controls.
- **`scripts/apply_capture_profile.py` / `scripts/capture_profile.py`** (not
  lane-owned): authored captured profiles keep their closed schema without
  `low_shelf`. That fails closed and is acceptable. Admitting the shelf there
  is a separate decision.
- No `just` recipe change is needed: `just clean INPUT fuller-shelf
  --capture-interval S E --capture-review TEXT` resolves through the existing
  profile-name lookup. Root confirms this at integration.

## 10. Phase 2 outcome (appended after implementation; sections 1–9 unchanged)

Implemented as frozen. The receipt is
`docs/agent-notes/sprints/20261007-s2r/eq_shelf-20261007-run.json`.

- **Contract (C).** `low_shelf` is validated in `validate_post_controls`
  (`validate_low_shelf`, `validate_review_status`) and rendered first by
  `post_denoise_filters`. `load_profile` refuses a repeated `low_shelf` key via
  an `object_pairs_hook`; every other key keeps json's last-wins behaviour.
  Peaking EQ, `fuller.json` (sha256 unchanged) and `DEFAULT_PROFILE` are
  untouched. All seven existing profiles have byte-identical stage lists
  against the frozen 7d0e11e source and against a static pin.
- **Measured (M), synthetic F1 only.** E1 shelf-only C1 delta is +1.480 dB
  (1/1, pass band (0, +2.0]). 9/9 components are not cut; the smallest delta
  is +0.023 dB at k=9. E2 (P′ vs P, compressor included, no loudnorm) gives a
  C1 delta of +1.407 dB. Components k=7..9 (229–294 Hz) are −0.028 to
  −0.071 dB in E2. Those are compressor level interaction, not a shelf cut,
  and are reported only.
- **Inference (I).** RBJ analytic C1 is +1.480 dB; the measured-minus-analytic
  difference is 0.000 dB (all 9 components agree within 0.0001 dB). The
  section 7 expectation that k ≥ 5 would be about +0.1 dB or less was
  slightly low: k=5 is +0.192 dB in both measurement and theory.
- **Unknown / not performed.** The optional E3 real-take arm was not run, so
  `real_take_effect_in_chain` is `unknown`. Listening is `not_performed`.
