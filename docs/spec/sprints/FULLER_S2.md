# S2 lane fuller_profile: reproducible FULLER profile and marked-compact recipe

Sprint 20261006-s2, Linear TIN-5600 (related TIN-5487). Lane branch
`sprint/20261006-s2/fuller_profile`, worktree `.local/sprint2/fuller_profile`.
Authority: S2 lane contract relayed by root; repository AGENTS.md;
R-HOOK-CONVERGENCE-20261004 / R-N11 / R-N12 / R-N13. Phase 1 contract freeze;
no numerics ran while it was written. The lane never pushes, merges, writes
Linear, flips a default or adopts a master. Root signs and integrates.

## 1. Scope

1. **`profiles/fuller.json`**: the operator-approved FULLER-v1 chain, copied
   exactly from the accepted run and not re-derived. A reviewed per-take capture
   interval is a **required input** and is never baked into the profile.
2. **`scripts/marked_compact.py`**: a reusable CLI version of the one-off
   `docs/agent-notes/2026-10-06-accepted-fuller-compact-assembly.py`. It takes
   RUN_DIR (the audio branch) plus a verified arrangement-marker compact picture
   preview and produces a compact marked movie. It keeps the exact picture/AAC
   packet, clock, padding and decoded-PCM copy checks from the assembly result.
3. **Root change requests (lane does not apply them):** typed capture refusals
   and per-take `--capture-interval` input in `scripts/media.py`; matching
   passthrough in `scripts/run_demo.py`, `scripts/tool_api.py`,
   `program/tools.json` and `just/workflow.just`; a `marked-compact` just recipe;
   and the optional default flip from conservative3 to fuller. See section 8.

Out of scope: new DSP settings, tuning, NR10, model work, new listening claims,
master/latest promotion, editing the accepted run or any Desktop/Documents file,
any edit to `conservative3.json` (it stays available and stays the default in
the lane commit).

## 2. Accepted FULLER-v1 identity (source of truth, read-only)

| Item | Value |
| --- | --- |
| Accepted run | `artifacts/runs/20261006T041633Z-990aa1bd6737` (main checkout) |
| Manifest / applied profile / application receipt | `61c9b393…a750a5f` / `a1229c84…f4b826` / `ab1f31df…e7e48` |
| Original source | `a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`, mono 44100 Hz, 6,657,385 samples, origin 0 |
| Reviewed capture | 4.10–4.95 s = samples [180810, 218295); contamination **unknown** (operator reported pre-5 s guitar/amp sounds and mechanical wind-up). This is not a verified noise-only interval. |
| Accepted audio | cleaned.wav `9ed50aeca1345204959f1f72acc368a42045b568542150971a68119056cb2009`; export video `91b2f436…a04a82` |
| Acceptance | `docs/agent-notes/2026-10-06-fuller-listening-acceptance.json` (`0f8d3dbf…`): operator QuickTime feedback “sounds excellent!  great work!”, relayed by root. Covers this exact audio only; NR8/NR10, master adoption, analysis accuracy and sync are not covered. |
| Code at render | media.py `91443154…a9d94`, apply_capture_profile.py `790ac58f…6584` (both unchanged in this worktree at freeze) |
| FFmpeg | `ffmpeg version 8.1.2` at `/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin`, 2 threads |

Accepted controls, copied verbatim from `applied-profile.json`. JSON numeric
types must stay the same (floats stay floats) so that the generated filter text
is byte-identical, for example `nr=8.0` and `I=-18.0`:

`denoise true; reduction_db 8.0; noise_floor_db -40.0; adaptivity 0.0;
gain_smooth 0 (int); preserve_low_fundamental_hz 32; integrated_lufs -18.0;
true_peak_dbtp -1.75; peaking_eq [{160.0, +2.0, q 0.7}, {300.0, +1.0, q 0.8}];
compressor {threshold_db -18.0, ratio 2.0, attack_ms 15.0, release_ms 100.0,
knee_db 3.0}`. There is no high-pass, no hum notch and no 2.2 kHz boost.

Accepted filter strings (from the manifest `commands`):

- L (latency calibration): `afftdn=nr=8.0:nf=-40.0:tn=0:gs=0:ad=0`
- C (capture/denoise graph): `[0:a]asplit=2[noise][body];[noise]atrim=start_sample=180810:end_sample=218295,asetpts=N/SR/TB,apad=pad_len=4410[training];[body]asetpts=N/SR/TB[take];[training][take]concat=n=2:v=0:a=1,apad=pad_len=1102,asendcmd=c='0 afftdn sn start;0.85 afftdn sn stop',afftdn=nr=8.0:nf=-40.0:tn=0:gs=0:ad=0,atrim=start_sample=42997:end_sample=6700382,asetpts=N/SR/TB[out]`
- P (post-denoise): `equalizer=f=160:t=q:w=0.7:g=2:b=0:r=f64,equalizer=f=300:t=q:w=0.8:g=1:b=0:r=f64,acompressor=threshold=0.125892541179:ratio=2:attack=15:release=100:knee=1.41253754462:makeup=1:level_in=1:mode=downward:link=maximum:detection=rms:mix=0.25`
- N (normalization target prefix, both passes): `loudnorm=I=-18.0:TP=-1.75:LRA=50`; two-pass linear requested, rendered to pcm_s24le

**"Equal modulo the interval" is defined as follows.** The template
T(s, e, n, r, d) is built from C by substituting the noise `start_sample=s`,
`end_sample=e`, the guard `pad_len=g` with g = ceil(r/10), the delay
`pad_len=d`, the stop time `(e−s)/r` formatted `.12g`, and the final
`atrim=start_sample=(e−s)+g+d:end_sample=(e−s)+g+d+n`. The tests require
**both** T(180810, 218295, 6657385, 44100, 1102) == C byte for byte **and**
fixture C_f == T(s_f, e_f, n_f, 44100, d_f), where d_f is the fixture's
measured delay (predicted 1102). L, P and N must be equal byte for byte with
no substitution.

## 3. Owned files

- `profiles/fuller.json`
- `scripts/marked_compact.py`
- `tests/test_fuller_profile.py`
- `tests/test_marked_compact.py`
- `docs/spec/sprints/FULLER_S2.md` (this file)
- `docs/agent-notes/sprints/20261006-s2/fuller_profile-*.json` (freeze and run receipts)

Runtime outputs go only under `.local/sprint2/fuller_profile/artifacts/s2/fuller_profile/`
(gitignored). The lane reads `artifacts/runs/*` and `artifacts/experiments/*`
and never writes them.

## 4. Deliverable contracts

### 4.1 profiles/fuller.json (template)

- The schema_version 1 closed schema plus one new boolean key,
  `"noise_capture_required": true`. The key is requested from root (RQ-M1). It
  has no `noise_capture_seconds`, `noise_capture_source_sha256`,
  `noise_capture_authorized` or `noise_capture_review`, because per-take
  binding supplies them.
- **Fails closed before root merge.** The current `media.load_profile` rejects
  the unknown key ("profile contains unsupported fields"), so it never silently
  runs a fixed-floor non-FULLER denoise under the fuller name.
- The description states its scope. Operator listening acceptance covers only
  the identical chain on source `a522115f…` with capture samples
  [180810, 218295). Any other take or interval is `not_performed`. It makes no
  claim of 32 Hz restoration, noise-only capture or tone suitability on other
  takes.
- `preserve_low_fundamental_hz` is 32, and the profile has no
  high-pass/low-shelf-cut/notch stage. `validate_post_controls` and
  `post_denoise_filters` accept it, and the result equals P exactly.

### 4.2 Per-take binding (RQ-M1, root applies in media.py)

- `clean INPUT [PROFILE] [--capture-interval START END --capture-review TEXT]`
  and `demo INPUT [--profile P] [--capture-interval START END --capture-review TEXT]`.
- Binding sets `noise_capture_seconds=[START,END]`,
  `noise_capture_authorized=true`, `noise_capture_review=TEXT` and
  `noise_capture_source_sha256=<hash of INPUT>`, then runs the unchanged
  existing validation and render path.
- `MediaError` gains a `code` attribute. CLI error JSON adds
  `"reason": code`. Typed reasons:

| Reason code | Condition | Refusal point |
| --- | --- | --- |
| `capture_interval_required` | profile has `noise_capture_required: true` and no interval was supplied | before source hashing or decode; no run or staging directory |
| `capture_review_required` | interval supplied without non-empty review text (at most 2000 chars) | before decode |
| `capture_interval_invalid` | non-finite values, start < 0, or a duration outside 0.1–10 s | before decode |
| `capture_interval_conflict` | the profile already binds an interval and the CLI supplies another | before decode |
| `capture_source_mismatch` | the bound source SHA differs from INPUT | before decode (existing check) |
| `capture_interval_outside_source` | interval ends beyond the decoded extent | after decode, before any render (existing two checks); staging removed |

- Existing source-bound profiles (captured8/12/clarity) keep working unchanged.
  `conservative3`/`mild6`/`bypass` stay unchanged.
- **Before merge** the lane proves the chain through the current media.py by
  materializing a bound profile from the template (removing
  `noise_capture_required` and adding the four capture keys) and calling
  `media.clean`. **After merge** the same tests also run the CLI path. Those
  tests skip with the explicit reason `requires root RQ-M1` only while
  `media.MediaError` lacks `code`.

### 4.3 scripts/marked_compact.py

```
python3 scripts/marked_compact.py RUN_DIR --picture-preview PREVIEW_DIR \
    --arrangement-markers RUN_RELATIVE_SELECTOR [--output FRESH_DIR] [--timeout-seconds 600]
```

- **RUN_DIR (audio branch, read-only).** `manifest.json` and
  `export/outcome.json` with `source_hash_verified`,
  `video_frame_count_preserved`, `relative_audio_video_start_verified`,
  `dsp_latency_compensation_recorded` and `final_true_peak_within_target` all
  true. `video_packet_expected_translation_seconds == 0`.
  `physical_audio_video_sync_verified == false`. The
  `export/cleaned-video.mov` hash must equal the outcome receipt.
- **PREVIEW_DIR (picture/marker branch, read-only).** A `marked_video.py`
  outcome with status `marked_review_preview_verified_unreviewed` and
  `marker_mode == arrangement_reference_review`.
  `arrangement_marker_selector == --arrangement-markers`. The
  `marked-video.mov`/`selection.json`/`callouts.ass` hashes must equal the
  outcome, and every `input_sha256` entry must still match. The markers are
  re-validated with `arrangement_markers.load_validated(preview_run, selector)`,
  and the resulting bindings must equal the outcome's
  `arrangement_marker_bindings`.
- **Branch gate, generalized from the one-off.** Both branches must share the
  same source SHA and the same native PCM `{sample_rate, channels,
  sample_count}`. The preview run is read from its manifest; for RUN_DIR it is
  the manifest `pcm`. Container, audio and picture origins must be 0 (other
  origins refuse with `nonzero_origin_unsupported` in v1), with no time
  stretch. Decoded picture extent and frame count are read from preview
  `verification` and are never hard-coded. Header audio duration must be at
  least the picture extent.
- **Composition.** Stream copy only:
  `-copyts -i picture -i audio -map 0:v:0 -map 1:a:0 -map_metadata 0 -map_chapters -1 -c:v copy -c:a copy -video_track_timescale <1/tb> -avoid_negative_ts disabled -movflags +faststart`.
  Two threads. The owned bounded runner and deadline are reused from
  `apply_capture_profile` (`Deadline`, `run_owned`), with a 600 s default and
  no retry. There is no audio DSP, normalization or picture encode.
- **Checks: exact equality with zero tolerance.** Ordered video packet payload
  hash and rational PTS/DTS/duration (via `media.video_packets` and
  `compare_video_packets` with zero translation, plus an exact rational
  comparison). AAC payload hash, rational timing, and skip_samples /
  discard_padding side data. The decoded AAC `pcm_f32le` SHA-256. The picture
  format keys (geometry, codec, profile/level, pix_fmt, color, extradata hash)
  and AAC format keys with extradata hash. Composed stream origins must be 0,
  AAC header extent must be unchanged, and all protected input hashes must be
  the same before and after.
- **Output.** A fresh directory under `<ROOT>/artifacts/` but not under
  `artifacts/runs/`. It must not be inside either parent, must have no symlink
  components, and is created `0700`. The default is
  `artifacts/experiments/marked-compact-<UTC>-<hex12>`. It contains
  `start.json`, `marked-compact.mov`, the parent/output packet tables, and
  either `receipt.json` (status `marked_compact_composition_verified`) or
  `failure.json` (status `marked_compact_failed_preserving_parents`, with
  `reason`). It is never overwritten (`open('x')`, ffmpeg `-n`).
- **Typed refusal reasons.** `run_dir_invalid`, `export_unverified`,
  `preview_unverified`, `arrangement_markers_mismatch`, `source_mismatch`,
  `native_pcm_mismatch`, `nonzero_origin_unsupported`,
  `audio_does_not_cover_picture`, `output_invalid`, `input_changed`,
  `packet_identity_failed`, `pcm_identity_failed`, `format_identity_failed`,
  `deadline_exceeded`, `ffmpeg_failed`. The CLI prints
  `{"status":"error","reason":…,"error":…}` and exits 1.
- **Chain identity and listening label.** `chain_identity(manifest)` sorts the
  audio branch into one of three classes:
  - `identical_accepted_fuller_v1`: the source SHA, capture samples
    [180810, 218295), native PCM, L, C, P and N, and the FFmpeg version line
    all equal the accepted values.
  - `fuller_v1_template_other_binding`: equal modulo the interval and extent
    per section 2.
  - `not_fuller_v1`: anything else.

  `listening_acceptance` is `accepted_fuller_v1_by_operator_2026-10-06` **only**
  for `identical_accepted_fuller_v1`, and only when cleaned.wav is
  byte-identical to `9ed50aec…`. If the chain is identical but the audio bytes
  differ, the label is `not_performed`, with reason
  `chain_identical_audio_differs`. Every other case is `not_performed`.
  `accepted_audio_identity` is `byte_identical`, `differs` or `not_compared`.

## 5. Explicit unknown and abstain fields the outputs must carry

Every marked_compact receipt, and every lane run receipt that applies, carries
these fields with exactly these values unless real evidence proves otherwise:
`capture_noise_only_verified: false`, `capture_music_status: "unknown"`,
`capture_click_status: "unknown"`,
`physical_audio_video_sync_verified: false`,
`fundamental_32hz_restoration_claimed: false`,
`per_passage_level_matched: false` (dynamic loudnorm changes passage gain),
`composite_visual_review_performed: false`,
`composite_listening_review: "not_performed"`,
`markers_are_analysis_of_audio_branch` (true only if the preview's
`analyzed_input_sha256` equals RUN_DIR's denoised.wav SHA, false otherwise),
`performance_issue_confirmed: false`, `note_correctness_assessed: false`,
`master_adopted: false`, `latest_promoted: false`,
`default_profile_changed_by_lane: false`, `native_editor_import_verified: false`,
`listening_acceptance`, `accepted_audio_identity`, and
`tone_suitability_other_takes: "unknown"`. Missing values stay `null` with a
reason. They are never omitted.

## 6. Test protocol (lane runs only these modules)

Run from the worktree root with
`FFMPEG=/nix/store/mv3x…-8.1.2-bin/bin/ffmpeg FFPROBE=…/ffprobe`:

```
PYTHONPATH=tests python3 -m unittest test_fuller_profile -v
PYTHONPATH=tests python3 -m unittest test_marked_compact -v
PYTHONPATH=tests python3 -m unittest test_media.ProfileTests test_arrangement_markers -v   # directly affected, read-only regression
```

### tests/test_fuller_profile.py

- `FullerProfileContractTests` (no FFmpeg):
  - The 19 accepted controls are equal by value **and** by Python type.
  - `noise_capture_required is True`, and no interval, source or review is
    baked into the profile.
  - P is exactly equal to `post_denoise_filters(profile, 44100)`.
  - No forbidden stage appears (`highpass`, `lowpass`, `bandreject`, notch,
    `anequalizer`), and `preserve_low_fundamental_hz == 32`.
  - The template at the accepted values reproduces C byte for byte.
  - conservative3.json keeps its SHA (`28bd2cf6…`), loads, and stays the
    media.py default (`main` argparse default unchanged in the lane commit).
- `FullerFixtureRenderTests` (requires FFMPEG/FFPROBE; skips with a reason
  only if they are absent; `media.ROOT` is set to a temp directory):
  - **Fixture:** 44100 Hz mono, 3.0 s plus 137 samples, `random.Random(914)`.
    Fan noise 0.008·U(−1,1) plus 0.003·sin(240 Hz) throughout. From 1.2 s:
    guitar 0.22·sin(32.703 Hz, C1) plus 0.06·sin(160 Hz) and a damped 5 ms
    2.1 kHz pick burst at 2.0 s.
  - Capture interval [0.2, 1.05] s gives samples [8820, 46305), a 0.85 s stop
    and guard 4410.
  - **Assertions:**
    - L, P and N are equal byte for byte.
    - C_f equals T(8820, 46305, n_f, 44100, d_f) with d_f == 1102.
    - The measured afftdn band update is present for 1 of 1 channel.
    - Every output keeps the native rate, channels and sample count.
    - `frequency_preservation` reports high-pass and notches false.
    - The coherent 32.703 Hz component of denoised.wav over 2.0–3.0 s is at
      least 0.9 × 0.22. This is a synthetic measurement only.
    - The source is unchanged.
  - **Refusals before merge** (direct `media.clean` on the materialized bound
    profile):
    - Interval [2.5, 3.4] past the extent is refused with the outside-source
      message class.
    - A wrong source SHA is refused with the source-mismatch message class.
    - Capture metadata without an interval is refused at load.
    - The raw template is refused at load (fail-closed).
    - Each refusal leaves 0 runs and 0 staging directories.
- `FullerTypedRefusalTests` (RQ-M1; skips only while `MediaError` has no
  `code`; root's integration run must show 0 skips): `media.main` `clean`
  **and** `demo` for each of the four codes `capture_interval_required`,
  `capture_review_required`, `capture_interval_outside_source` and
  `capture_source_mismatch`. That is 8 CLI cases, each with exit 1, JSON
  `reason`, and no run or staging directory left behind. A valid
  `--capture-interval` CLI render produces a C identical to the materialized
  pre-merge path.

### tests/test_marked_compact.py

- **Unit tests (no FFmpeg):**
  - `exact_packets` accepts equal rational times in different time bases.
  - It rejects shifted PTS, a changed payload hash, and changed
    skip_samples/discard_padding.
  - The branch gate rejects source mismatch, PCM mismatch, nonzero origin,
    unverified export or preview, and a selector mismatch.
  - Output validation rejects existing, symlinked, inside-parent and
    `artifacts/runs/*` targets.
  - `chain_identity` is checked on four cases built from embedded accepted
    constants: identical-and-byte-identical gives accepted; identical with
    different audio gives not_performed; another interval gives
    template_other_binding / not_performed; a changed EQ gives not_fuller_v1.
- **Real tiny-movie test** (requires FFmpeg; reuses
  `test_marked_video.create_verified_fixture(origin=0, vfr=True)` and the
  arrangement fixture pattern from
  `test_arrangement_markers.test_alternate_intent_preview_preserves_vfr_and_aac_without_canonical_edits`):
  - Render a real arrangement compact preview.
  - Build a second same-source audio run whose AAC differs, using a volume
    re-encode from the same original.
  - Compose, then assert `marked_compact_composition_verified`, k/k video and
    m/m AAC packets identical, an equal decoded PCM hash, and every protected
    parent file hash unchanged.
  - Assert the receipt carries every section 5 field, with
    `listening_acceptance == not_performed`.
- **Real refusal tests:**
  - A stale or edited arrangement marker file gives
    `arrangement_markers_mismatch`.
  - An audio run shorter than the picture gives `audio_does_not_cover_picture`.
  - An input mutated mid-run gives `input_changed`.
  - Each case leaves `failure.json` and no `receipt.json`.

## 7. Completion metrics (denominator; claim class)

| ID | Metric | Pass condition | Claim class |
| --- | --- | --- | --- |
| M1 | Control fidelity | 19/19 accepted controls equal by value and type | static measurement |
| M2 | Filter-graph identity | L, P, N 3/3 byte-equal; template at accepted values gives C 1/1; fixture C_f matches template 1/1 | fixture measurement |
| M3a | Pre-merge refusals | 4/4 refusal classes raised, 0 residual run/staging dirs | fixture measurement |
| M3b | Typed refusals after RQ-M1 | 8/8 CLI cases with exact `reason`; 0 skipped in root integration | fixture measurement (root-run) |
| M4 | Low-end guard | 0 forbidden stages; fixture C1 component ≥ 0.9× (1/1) | synthetic measurement only, not a real-take or listening claim |
| M5 | marked_compact synthetic | 1/1 compose with k/k video, m/m AAC, PCM 1/1, parents N/N unchanged; refusals 100% of listed cases with typed reason; chain_identity 4/4 | fixture measurement |
| M6 | Actual reproduction A1 (preregistered, section 9) | C byte-equal 1/1; WAV byte identity reported x/6 | real-take measurement; no listening claim |
| M7 | Actual marked-compact A2 (preregistered) | identity checks pass; video 3621/3621, AAC 6503/6503 packets; output SHA vs `4538573a…` reported | real-take measurement |
| M8 | Protection | accepted run 13/13 files (10 top-level incl. frame-count cache, 3 under export/), compact parent 4/4 plus marker file 1/1, Desktop `34247a4e…` 1/1 unchanged; lane diff touches only owned files; conservative3 default unchanged | integrity measurement |
| M9 | Claim hygiene | 0 new listening claims; accepted label appears only under the section 4.3 rule | review |

Experimental non-reproduction (for example A1 bytes differ) is a valid
completion. It is reported as is, and no control is changed to force a match.

## 8. Root-owned change requests (exact diffs supplied in the phase 2 return)

- **RQ-M1 `scripts/media.py`:** `MediaError(message, code="media_error")`; add
  `noise_capture_required` to the allowed keys (bool; requires `denoise`); add
  `bind_capture(profile, interval, review, source_sha256)`; add
  `clean(..., capture_interval=None, capture_review=None)` with the refusal
  table in section 4.2; add argparse `--capture-interval START END` and
  `--capture-review TEXT` on `clean` and `demo`; add `"reason"` to the CLI
  error JSON. Codes are attached to the existing refusals without changing
  their messages.
- **RQ-M2 default flip (optional, root decision; the lane does not apply it):**
  media.py:826 `restore.add_argument("profile", nargs="?", default="conservative3")`
  becomes `default="fuller"`. media.py:831
  `demo.add_argument("--profile", default="conservative3")` becomes
  `default="fuller"`. tool_api.py:646 `args.get('profile', 'conservative3')`
  becomes `'fuller'`, plus `--capture-interval`/`--capture-review` passthrough
  from new `capture_interval`/`capture_review` tool arguments in
  `program/tools.json` (`denoise`, default at :91).
  - **Consequence:** a default `clean INPUT` with no interval then refuses with
    `capture_interval_required`. This is intentional "required interval"
    behavior, but it changes existing calls.
  - **Recommendation:** keep `benchmark` (tool_api.py:654) and
    `run_demo.py:352` on conservative3 for synthetic suites unless root decides
    otherwise.
- **RQ-J1 `just/workflow.just`:**
  - `clean input profile="conservative3" *ARGS:` runs
    `python3 scripts/media.py clean {{quote(input)}} {{quote(profile)}} {{ARGS}}`.
  - `demo` passes `--profile` and `--capture-interval A B --capture-review TEXT`
    through to `run_demo.py`, which needs a matching passthrough at
    `scripts/run_demo.py:352,462`.
  - New recipe:
    `marked-compact run_dir *ARGS:` runs
    `python3 scripts/marked_compact.py {{quote(run_dir)}} {{ARGS}}`.
- **RQ-T1:** tool/skill admission for `marked_compact` (MCP hook plus
  `.agents/skills/` entry). Root admits it; the lane supplies the descriptor
  text only.

## 9. Preregistration (sealed in this commit, before any lane numerics)

This is a reproduction check, not a tuning experiment. It has one arm, the
fuller template bound to the accepted interval. There are no free parameters
and no held-out set. Fixture seeds and signals are frozen in section 6.

- **A1 (one heavy job, 600 s timeout, 2 threads).** Input: the original take
  (read-only). Materialize the bound profile [4.1, 4.95] and run `media.clean`
  with `media.ROOT=<lane>/artifacts/s2/fuller_profile/repro-A1`.
  - **Primary (sealed prediction: pass):** C, L, P and N are byte-equal to
    section 2. The capture samples are [180810, 218295) and the delay is 1102.
  - **Secondary (sealed prediction: 6/6 byte-identical):** the source,
    denoised, residue, processed, baseline and cleaned SHA-256 values against
    the accepted manifest.
  - If secondary is below 6/6, report each stage's max absolute sample
    difference and RMS difference in dBFS, and label `accepted_audio_identity:
    differs`. No change is made to controls or code.
- **A2 (copy-only, 600 s bound).** Inputs: RUN_DIR = the accepted run,
  PREVIEW = the NR10 `reference-marked-preview-compact` (`3a8eacb7…`), and
  selector `arrangement-reference-20261006/arrangement-markers.json`
  (`b82c447d…`). Output under `<lane>/artifacts/s2/fuller_profile/`.
  - **Primary (prediction: pass):** all section 4.3 checks; 3621 video and
    6503 AAC packets; `listening_acceptance` (audio branch) is the accepted
    label; `markers_are_analysis_of_audio_branch` is false.
  - **Secondary (prediction: byte-identical to `4538573a…`, unknown):** a
    mismatch with passing packet and PCM identity is reported, not treated as
    a failure.
- **Scoring:** exact predicates only. Truth (the accepted hashes) is already
  frozen in `fuller_profile-phase1-freeze.json`. Results go to
  `docs/agent-notes/sprints/20261006-s2/fuller_profile-A1.json` and
  `-A2.json`, with protected hashes recorded before and after. A1 and A2 run
  one at a time and never concurrently.

## 10. Phase 2 implementation record (additive; sections 1-9 stay frozen)

Recorded 2026-10-06 by the lane. Receipts:
`docs/agent-notes/sprints/20261006-s2/fuller_profile-A1.json`, `-A2.json`,
`-root-requests.json` and `-phase2-completion.json`.

### 10.1 Results against section 7

| ID | Result | Claim class |
| --- | --- | --- |
| M1 | 19/19 controls equal by value and Python type | static measurement |
| M2 | L, P, N 3/3 byte-equal; T(accepted) == C 1/1; fixture C_f == T(8820, 46305, 132437, 44100, 1102) 1/1 | fixture measurement |
| M3a | 4/4 pre-merge refusal classes; 0 residual run or staging directories | fixture measurement |
| M3b | 8/8 CLI cases with exact `reason`, 0 skipped, **in a lane scratch tree with the RQ-M1 diff applied**; root must repeat in integration | fixture measurement (prototype; root-run pending) |
| M4 | 0 forbidden stages; fixture denoised C1 component 0.21899 vs source 0.21899 (bound 0.198) | synthetic measurement only |
| M5 | 1/1 compose with k/k video and m/m AAC packets, decoded PCM equal, parents unchanged; real refusals 3/3 typed; chain_identity 4/4 | fixture measurement |
| M6 | A1 primary pass (C, L, P, N byte-equal; samples [180810, 218295); delay 1102); WAV byte identity 6/6 | real-take measurement; no listening |
| M7 | A2 pass: video 3621/3621, AAC 6503/6503; output SHA equals `4538573a...` (byte-identical) | real-take measurement |
| M8 | 21/21 protected files unchanged before/after A1 and A2 (13 accepted run, 4 compact parent, 1 marker, 2 accepted compact, 1 Desktop); lane commits touch only owned files; conservative3 default unchanged | integrity measurement |
| M9 | 0 new listening claims. The accepted label appears only on the identical chain with byte-identical audio (A1 run, A2 audio branch) | review |

Both sealed predictions held, including the two secondaries (6/6 WAV identity
and the byte-identical compact). A1 used 462 s of its 600 s bound, so the
bound is tight for a 151 s take on this host.

### 10.2 Implementation choices and tightenings (no frozen predicate loosened)

1. `listening_acceptance` additionally requires `export/cleaned-video.mov`
   to equal the accepted export `91b2f436...` whenever the export hash is
   evaluated. The acceptance receipt names that file. A mismatch yields
   `not_performed` with reason `chain_identical_export_differs`.
2. marked_compact adds a catch-all reason, `internal_error`, for unexpected
   exceptions, so no failure is mislabelled with a typed reason.
3. The marked_compact gate order is: export, then preview status, then the
   marker selector and revalidation, then the preview input hashes. An edited
   marker file therefore reports `arrangement_markers_mismatch` and not
   `preview_unverified`.
4. Protected inputs include every top-level file of RUN_DIR and RUN_DIR/export,
   the preview outputs and outcome, every preview `input_sha256` entry, the
   marker tracking set and `artifacts/latest.json` when present.
5. Chain helpers (`capture_template`, `extract_chain`, `chain_identity`) live in
   `scripts/marked_compact.py`, so tests and receipts share one definition.
   `capture_template` builds T from the section 2 formula; tests prove it
   reproduces the accepted C byte for byte.
6. The RQ-M1 prototype runs `capture_review_required`, `capture_interval_invalid`
   and `capture_interval_conflict` before source hashing. That is stricter than
   "before decode". `bind_capture` drops `noise_capture_required` from the
   bound profile, so manifests match the materialized pre-merge path.

### 10.3 Consequences root must weigh

- **Editing the `denoise` descriptor in `program/tools.json` (MCP passthrough)**
  breaks `test_sprint1_audit.AdmissionCompatibilityAudit.test_original_thirty_descriptors_remain_exact`,
  which pins the hash of the first 30 descriptors. The request is therefore
  split. RQ-M1 (media.py) and RQ-J1 (run_demo/just) do not touch the pin.
  RQ-M1b (tools.json plus tool_api denoise passthrough) needs root to rebase
  that pin, or to defer the MCP path.
- **Any media.py edit changes its SHA.** `apply_capture_profile.validate`
  requires the authored receipt's `validator_sha256` to equal the current
  media.py, so earlier authored capture receipts (captured8/NR8/NR10/FULLER
  authoring) can no longer be re-applied through that worker after RQ-M1. Root
  can still re-author them. The FULLER template plus `--capture-interval` is
  the replacement path, and A1 shows it reproduces the accepted bytes.
- **RQ-M2 (default flip).** A default `clean INPUT` with no interval refuses
  with `capture_interval_required`. `just clean` passes its own
  `profile="conservative3"` default, so the recipe default only changes if
  root edits it too. Flipping `tool_api` without RQ-M1b leaves MCP `denoise`
  unable to supply an interval. The lane test
  `test_conservative3_unchanged_loadable_and_still_default` asserts the lane
  state, and the exact replacement for a flip is in the root-requests receipt.
