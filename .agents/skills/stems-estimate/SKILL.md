---
name: stems-estimate
description: Produce private, labelled htdemucs_6s stem estimates from a source-timed excerpt of the mono nine-string take, with the 20-45 Hz band energy of each estimate measured against the input; never a recovered stem, never a cleanup/tone/master default, and refused until root registers the hash-bound checkpoint, the operator acknowledges the weights' terms and a runtime is qualified.
---

# Estimate stems from the mono take (htdemucs_6s, experimental)

**Hook:** MCP tool `stems_estimate`, **draft only**. The descriptor is in
`program/tool-drafts/stems_estimate.json` and root admits it into
`program/tools.json`. Worker: `scripts/stems_estimate.py`. Contract:
`docs/spec/sprints/STEMS_S3.md`.

**Status (2026-10-07):** `program/models.json` has no
`demucs-htdemucs_6s-5c90dfd2` entry. Every valid request therefore refuses
`model_not_registered`. No weights have been fetched and no inference has run.
That refusal is the designed behaviour, not a fault.

## Intent

The take is one distorted, down-tuned nine-string guitar (C1 = 32.70 Hz
theoretical), an in-room click and a large box fan, recorded on a phone in mono.
htdemucs_6s splits a mixture into six trained target labels: drums, bass, other,
vocals, guitar and piano. On this take the six outputs are the model's
**allocation** of one mono mixture. They are estimates, never recovered original
stems.

The tool gives listening review and agents a private comparison point. For
example: does the `guitar` estimate keep the C1 band, or did the model push it
into `bass`? Did click attacks go to `drums`?

It never gives a verdict. It is never a cleanup, denoise, tone, dynamics or
master input by default.

## Knobs

There are none. The fixed settings are recorded in
`runtime_identity.apply_settings`:
- `htdemucs_6s` single model, CPU, 2 threads;
- `shifts=1`, `overlap=0.25`, `split=true`, model-default `segment`;
- seed `20261007`;
- 600 s inference deadline and 3 GiB RSS ceiling.

The `apply_model` defaults and the `sources` order are recalled from upstream. A
separate runtime lane confirms them against the pinned package.

The request is closed-schema and has only these fields:

| Field | Rule |
| --- | --- |
| `run_dir` | run beneath `artifacts/runs/` (or a fixture case beneath `artifacts/s2/stems_contract/fixtures/`) |
| `input_role` | `denoised` (default) or `source` |
| `excerpt_start_seconds` | seconds from the run's `timeline.audio_start_seconds` |
| `excerpt_end_seconds` | the excerpt length must be 1.0-30.0 s |
| `timeout_seconds` | integer 1-900, default 660 |

Choose the excerpt **before** listening to or analysing its content. The
preregistered real-take excerpt is `[30.0, 60.0)` s of the accepted FULLER run
`artifacts/runs/20261006T041633Z-990aa1bd6737`. It skips the first five seconds
of setup sounds.

## Dependencies

All of these are explicit root or operator acts. The tool acquires nothing.

1. **Registry.** Root adds the entry from
   `program/model-drafts/htdemucs_6s.json` to `program/models.json`:
   - `sha256` comes from root's own hash-bound fetch of the 54,996,327-byte
     file;
   - the filename prefix `34c22ccb` is a cross-check only.
2. **Operator acknowledgement.** The operator acknowledges the maintainer's
   personal/research terms and the "risk" sentence. Root records the receipt
   reference as `operator_terms_acknowledgement`. If it is null, the tool
   refuses `model_terms_not_acknowledged`.
3. **Prefetch.** Root places `models/demucs-htdemucs_6s-5c90dfd2.bin` on the run
   host.
4. **Runtime.** A separate root-run lane prepares an isolated Linux CPU
   interpreter beneath `artifacts/model-runtime-env/` (honey). It pins `demucs`
   and `torch` by setting `DEMUCS_PIN`/`TORCH_PIN` in the worker. The worker
   finds the interpreter only through `VIDEO_UTILS_STEMS_RUNTIME_PYTHON`, and
   the interpreter path must not contain a symlink.
5. **Input.** A current verified run: mono, at most 300 s, input WAV bound by
   `manifest.output_sha256`, an explicit `timeline.audio_start_seconds` and a
   64-hex `source.sha256`. A prior `denoise` run is recommended.

## Use

```sh
python3 scripts/stems_estimate.py estimate --request-json \
  '{"run_dir":"artifacts/runs/<run>","excerpt_start_seconds":30.0,"excerpt_end_seconds":60.0}'
python3 scripts/stems_estimate.py estimate --request request.json   # or --request - for stdin
```

The exit code is 0 for completed, 2 for refused and 1 for failed. stdout carries
the refusal object, or a summary with `output_dir`. Output goes to a fresh
directory `artifacts/s2/stems_contract/estimates/<UTC>-<id>/`, which holds:
- `stems/<name>.wav`: float32 mono at the source rate, exactly `frame_count`
  frames, first frame at `excerpt.source_start_seconds`;
- `model_input.wav`: the analysed 44.1 kHz stereo input; its sha256 is
  `analysed_input.sha256`;
- `stems_estimate.json`.

The run directory is never written.

## Refusals

The tool fails closed. The first failure wins, and nothing is written on a
refusal:

1. `request_invalid`: extra or missing key, wrong type, non-finite number,
   end ≤ start, or excerpt shorter than 1.0 s.
2. `excerpt_too_long`: excerpt longer than 30.0 s.
3. `model_not_registered`: registry missing, symlinked, larger than 1 MiB,
   with the wrong schema, or without an entry.
4. `model_hash_not_registered`: `sha256` null or not 64 lowercase hex.
5. `model_registry_entry_invalid`: URL not HTTPS or carrying userinfo, licence
   empty, or `max_bytes` out of range.
6. `model_terms_not_acknowledged`.
7. `model_file_missing`: the model file is missing, symlinked or larger than
   `max_bytes`.
8. `model_hash_mismatch`.
9. `runtime_unavailable`, with `runtime_reason` set to one of
   `not_configured`, `platform_unsupported`, `path_rejected`, `not_pinned` or
   `identity_failed`.
10. `input_not_admitted`.

Faults after admission are `status: "failed"` with a `failure_code`:
- `inference_failed`;
- `separator_output_invalid`;
- `round_trip_length_mismatch` (more than 2 frames);
- `input_or_model_changed`;
- `resampler_unavailable` or `resampler_failed`;
- `internal_error`.

## Evidence (reading `stems_estimate.json`)

The top-level keys form a closed set: contract section 7 plus 17 fixed
unknown/abstain fields.

- **Measured:** `low_end_check` gives the 20-45 Hz and 45-120 Hz band energies
  of the input and of every estimate. Details:
  - The filter is Butterworth-4 high-pass plus Butterworth-4 low-pass RBJ
    biquads, Q 0.5412 and 1.3066.
  - The first `min(0.25 s, 25 %)` of the excerpt is excluded so the filters can
    settle.
  - Energies are measured after the sample-rate round trip, at the source rate.
  - Read `guitar_vs_input_band_db`, `guitar_plus_bass_vs_input_band_db` and
    `per_stem.*.band_share_of_stem_sum` together.
  - A null comes with a `*_reason` key, such as `zero_input_band_energy`.
- **Measured:** `mixture_consistency` compares the sum of the six estimates
  minus the input against the input, full band and 20-45 Hz.
- **Recorded:**
  - `analysed_input.sample_rate_conversion` (FFmpeg `aresample=…:resampler=swr`
    filter strings, applied only when the source rate is not 44.1 kHz) and
    `length_adjust_frames`;
  - `channel_conversion` (`mono_duplicated_to_stereo`, `stereo_mean_to_mono`);
  - source-timeline origin and frames.
- **Never claimed:** these fields are fixed:
  - `recovered_original_stem: false`;
  - `instrument_presence_claim: "none"`;
  - `separation_accuracy: "unknown"`;
  - `low_end_preservation_verdict: null`;
  - `listening_accepted: false`;
  - `bleed_artifact_review: "not_performed"`;
  - `in_room_tone_recreated: false`;
  - `note_correctness`, `performance_issue` and `expected_rhythm_reference`
    are null;
  - `default_adoption`, `cleanup_default` and `master_eligible` are false.
- **Privacy:** real-take outputs carry `privacy:
  "V6_private_real_take_derived"` and `redistribution_permitted: false`. They
  stay in ignored artifacts.

## Research

- `docs/research/2026-10-07-stems-weights-licence.md` gives the verdicts:
  - htdemucs, htdemucs_ft and htdemucs_6s are `admissible_private_comparator`
    under five conditions;
  - the RoFormer candidates are held or excluded;
  - the MUSDB18-HQ terms are non-commercial;
  - the code licence never covers the weights.
- `docs/spec/sprints/STEMS_S3.md` is the contract and preregistration.
- `docs/research/FOSS_AUDIO_MATRIX.md` row 11 and `docs/spec/PROJECT.md`
  (stems are estimates from a mono mixture).
- Upstream: <https://github.com/facebookresearch/demucs> (MIT code, archived at
  `e976d93e`), and the maintainer's weight-terms statements in
  <https://github.com/facebookresearch/demucs/issues/327#issuecomment-1134828611>
  and
  <https://github.com/facebookresearch/demucs/issues/384#issuecomment-1262197483>.

## Iteration

- **Preregistered experiment.** STEMS_S3 section 8 defines suite `s3-stems-1`:
  - the cohorts are k1 C1 chugs, k2 low sustain, k3 high legato over C1 pedal,
    and k4 negative;
  - dev seed 4001 is smoke only;
  - held-out seeds are 4103 and 4211, giving 8 cases.
- **Protocol:** `generate-suite` → `predict --arm A0|A1` → `seal` → `score`.
  - Held-out generation itself refuses until A1 is runnable.
  - The scorer refuses unless a matching seal predates it.
  - The scorer refuses dev suites.
- **Metrics:** S1 low-band retention and band correlation, S2 SI-SDR, S3 fan
  leakage by least-squares projection, and S4 false allocation on k4. Each is
  reported as medians with every case listed.
- **Decision rule.** The rule is descriptive only. "No separation benefit
  shown" and `low_band_loss_observed` are valid outcomes. Either way, every
  default stays unchanged.
- **Real take.** The real-take pass on `[30, 60)` s reports measurements only.
  It needs the registry entry, the acknowledgement, the runtime and root's
  confirmation of the private scratch path.
- **Changes.** Do not tune to truth. Any change to the worker, the settings or
  the checkpoint is a new experiment with new seeds, reported separately.
