---
name: guitar-beat-this
description: DRAFT (S3 model_lanes, not admitted). Compare Beat This (CPJKU final0) beat and downbeat hypotheses against the project click grid on a verified run or generated fixture, through an isolated Linux CPU runtime and a registry-verified local checkpoint; meter, intended tempo and real-take accuracy stay unknown.
---

# Compare learned beat hypotheses (Beat This, experimental)

**Status:** draft. Root still has to admit three things:
- the `program/tools.json` descriptor `beat_this_compare`;
- the MCP hook;
- the `just` recipes.

Until then, call the worker directly. It is never a default detector and never
replaces `rhythm`/`bpm`/`clicks` output.

## Intent

Beat This is a second, independent beat/downbeat estimator. It shows where a
learned model's pulse agrees or disagrees with the project's heuristic click
grid. Typical disagreements are half-time feels, 7/8 groupings, drift, rests and
legato runs.

It gives listening and agent iteration a comparison point. It never gives a
verdict.

## Prerequisites (explicit and root-run; the tool never acquires anything)

1. **Registry.** Root adds the `program/models.json` entry
   `cpjku-beat-this-final0` after its own hash-bound fetch. The draft text is in
   `docs/research/BEAT_THIS_QUALIFICATION.md`. Then root runs
   `just model-prefetch cpjku-beat-this-final0`. The placeholder sha256 is
   refused by design.
2. **Runtime.** On honey, inside `nix develop .#ml`, root runs:
   `python3 scripts/beat_this_runtime_setup.py --python "$(command -v python3)"`.
   The runtime is Linux only. Four hash-pinned wheels are extracted offline. Torch
   comes from the ml shell as recorded system site packages.
3. **Verification:** `python3 scripts/beat_this_runtime_setup.py --check`. It is
   read-only, with no download or install.

## Use

```sh
python3 scripts/beat_this_compare.py compare --run-dir artifacts/runs/<run>
python3 scripts/beat_this_compare.py compare --fixture-wav artifacts/s2/model_lanes/fixtures/<suite>/cases/<case>.wav \
    [--generated-truth artifacts/s2/model_lanes/fixtures/<suite>/truth/<case>.json]   # dev suites only
```

There are no knobs. The fixed settings are:
- `final0`
- CPU
- `float16` off
- DBN off
- upstream minimal postprocessing
- 2 threads
- 600 s deadline
- 2 GiB RSS ceiling

Input rules:
- Real input is the manifest-verified `denoised.wav` of a run (≤300 s), with an
  explicit `timeline.audio_start_seconds`.
- Output goes to a fresh directory beneath `artifacts/s2/model_lanes/`.
- Accepted runs are never written.

## Refusals (fail closed, typed, in this order)

1. `model_not_registered`
2. `model_hash_not_registered`
3. `model_registry_entry_invalid`
4. `model_file_missing`
5. `model_hash_mismatch`
6. `runtime_not_qualified`
7. `platform_unsupported`
8. `input_rejected`

The tool never falls back and never downloads.

## Reading `beat_this_comparison.json`

- **Beat and downbeat lists.** `beats[]` / `downbeats[]` carry `model_seconds`
  and `source_timeline_seconds`. They are model hypotheses. `downbeat_semantics`
  is `model_hypothesis_not_bar_line`.
- **Tempo from model output.** `median_ibi_seconds` and `ibi_tempo_bpm` are
  measurements on the model's output, not the intended tempo
  (`tempo_identity: "unknown"`).
- **Half/double ratio.** `half_double_ratio_vs_click_grid.ratio` = click-grid
  period / median IBI. The nearest relation is one of 1/3, 1/2, 2/3, 1, 3/2, 2
  or 3 within 4 %, otherwise `unrelated`. A ratio of `2` means Beat This pulses
  twice as fast as the grid. It is arithmetic, not an identification of what
  the player intended.
- **Fixture scores.** `generated_truth_scores` (F70) exists only for dev-suite
  fixtures. Real takes carry `null` with `no_generated_truth`.
- **Fixed fields.** `meter_claim: "none"`, `time_signature: null`,
  `note_correctness: null`, `performance_issue: null`,
  `expected_rhythm_reference: null`, `listening_accepted: false` and
  `default_adoption: false` are fixed.
- **Privacy.** Real-take outputs carry `privacy: V6_private_real_take_derived`
  and stay in ignored artifacts.

## Research, iteration, evidence

- **Research:** `docs/research/BEAT_THIS_QUALIFICATION.md` covers the licence,
  checkpoint bytes, preprocessing (22.05 kHz, 50 fps, mel `f_min` 30 Hz) and the
  deviations from upstream known-working versions.
- **Preregistered experiment:** `docs/spec/sprints/MODEL_LANES_S3.md` section 7,
  suite `s3-beat-1`.
  - Held-out seeds are 3101 and 3203. Dev seed 3001 is smoke only.
  - The protocol is `generate-suite` → `predict --arm A0|A1` → `seal` → `score`.
  - The scorer refuses without a matching earlier seal.
  - The decision rule is descriptive only.
- **Iteration:** compare A0 (`rhythm.analyze` defaults) against A1 per cohort.
  Inspect half/double counts. Listen to disagreements. Do not tune Beat This to
  truth: there are no knobs, and any change is a new experiment with new seeds.
- **Never claim** missed or extra notes, meter, bar lines, performance grades or
  real-take beat accuracy from this tool.
