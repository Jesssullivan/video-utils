# S3 stems_contract lane contract (phase 1 freeze and preregistration)

Lane `stems_contract`, sprint `20261007-s3`, Linear TIN-5721. Branch
`sprint/20261007-s3/stems_contract`, worktree `.local/sprint3/stems_contract`.
Root signs the merge. Authority: the "Model lanes" operator decision row in
`docs/spec/sprints/20261007-S3.md` ("stems (Demucs/RoFormer) after weights
licence qualification"), the repository AGENTS.md, the V6 ruling in
`docs/agent-notes/2026-10-07-s2-operator-rulings.md`, and
R-HOOK-CONVERGENCE-20261004 (R-N11/R-N12/R-N13).

Inputs this contract builds on (read in phase 1, not re-verified here):
- `docs/research/2026-10-07-stems-weights-licence.md`: `htdemucs_6s`
  (`5c90dfd2-34c22ccb.th`, 54,996,327 B by `HEAD`, 2022-12-07) is the single
  recommended checkpoint, verdict `admissible_private_comparator` under five
  conditions (personal/research use; no redistribution of weights or real-take
  outputs; outputs under ignored `artifacts/`; outputs labelled estimates;
  explicit operator acknowledgement of the maintainer's "risk" sentence before
  first use). The code licence (MIT) never covers the weights.
- `docs/spec/sprints/MODEL_LANES_S3.md` and `scripts/beat_this_compare.py`: the
  fail-closed refusal order, registry resolution, child-process isolation and
  seal-before-truth patterns this lane reuses.
- `program/models.json` entry shape (`cpjku-beat-this-final0`), and the closed
  descriptor shape of `program/tools.json` / `scripts/tool_api.py`
  (`SUPPORTED_SCHEMA_KEYS`, `additionalProperties: false`). Both are root-owned
  and read-only here.
- `docs/spec/PROJECT.md` line 233 and `docs/research/FOSS_AUDIO_MATRIX.md` row
  11: stem outputs from a mono mixture are estimates; C1 guitar may leak to
  `bass`, click attacks to `drums`.

This file is the lane's frozen contract **and** its preregistration (section 8).
Phase 1 ran no numerics, generated no fixture, downloaded nothing, imported no
torch, and read no truth.

## 1. Scope

The take is a mono phone capture (AAC 44.1 kHz mono, decoded to `pcm_f32le`
44.1 kHz mono in run manifests) of one distorted nine-string guitar with
fundamentals down to C1 = 32.70 Hz (theoretical, A4 = 440), an in-room click
and a large box fan. There are no vocals, bass or drums. A separator's six
outputs are therefore the model's **allocation** of one mixture to six trained
target labels. Every output is an estimate from a mono mixture, never a
recovered original stem. A `bass`, `drums`, `vocals` or `piano` output does not
assert that such an instrument is present.

Deliverables (none changes a default detector, profile, master, catalog entry,
registry or recipe):

1. `scripts/stems_estimate.py`: a stdlib worker with a closed-schema request and
   result.
   - Today it refuses with `model_not_registered`: no weights fetched, no
     network, no torch/torchaudio/demucs/numpy import at module import time or on
     any refusal path.
   - Given a registered hash-bound checkpoint, an operator terms
     acknowledgement in the registry and a qualified isolated runtime, it runs
     `htdemucs_6s` on a source-timed excerpt (≤ 30 s) of a manifest-verified
     run WAV and writes six estimate WAVs plus `stems_estimate.json` with full
     provenance and a measured low-end check.
   - The runtime path is exercised in tests through an injected fake separator
     and fake runtime (no torch).
   - It also carries the stdlib fixture generator, sealing and scoring for the
     preregistered experiment (section 8).
2. `tests/test_stems_estimate.py`.
3. `.agents/skills/stems-estimate/SKILL.md` (intent, knobs, dependencies,
   research links, iteration, evidence, refusals).
4. `program/tool-drafts/stems_estimate.json`: a closed-schema tool descriptor
   **draft**, shaped like an admitted `program/tools.json` entry. It is not
   admitted and nothing reads it at runtime.
5. `program/model-drafts/htdemucs_6s.json`: a registry entry **draft** with
   `sha256: null`. Nothing reads it at runtime; the worker reads only
   `program/models.json`.
6. Root requests (section 9) for `program/tools.json` admission, `tool_api`
   dispatch, the `program/models.json` entry and a `just` recipe.

Out of scope:
- downloading weights, wheels or the `demucs` package; running real inference
  in this lane (it requires root's fetch and a separately qualified runtime);
- a runtime setup script or wheel lock for torch/demucs (a later runtime lane);
- any cleanup, denoise, tone, master or default use of an estimate;
- listening acceptance, bleed/artifact listening review, in-room tone claims;
- note correctness, missed/extra notes, performance grading;
- RoFormer checkpoints (held or excluded by the research);
- any write under `artifacts/runs/*`, the original take, `~/Documents`
  or `~/Desktop`.

## 2. Owned files

| File | Change |
| --- | --- |
| `scripts/stems_estimate.py` | new worker, child-process inference entry, fixture generator, seal and scorer |
| `tests/test_stems_estimate.py` | new; fake-separator, refusal, round-trip, timeline, low-end, schema and no-network tests |
| `.agents/skills/stems-estimate/SKILL.md` | new skill draft |
| `program/tool-drafts/stems_estimate.json` | new descriptor draft |
| `program/model-drafts/htdemucs_6s.json` | new registry entry draft |
| `docs/spec/sprints/STEMS_S3.md` | this contract |
| `docs/agent-notes/sprints/20261007-s3/stems_contract-*.json` | dated receipts |

Generated outputs go only under `artifacts/s2/stems_contract/` (gitignored):
`estimates/<UTC>-<id>/` for worker outputs and `fixtures/<suite>/` for the
experiment. Accepted runs under `artifacts/runs/*` and the original take are
read-only.

## 3. Model identity and registry draft

- Model id: `demucs-htdemucs_6s-5c90dfd2` (matches the `model_prefetch.py` id
  pattern; the local file is `models/demucs-htdemucs_6s-5c90dfd2.bin`).
- Upstream: `https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/5c90dfd2-34c22ccb.th`.
- Expected bytes: 54,996,327 (research `HEAD`, not a body read).
- Upstream partial hash: filename suffix `34c22ccb` is the first 8 hex digits of
  the file's sha256 per Demucs convention. It is a cross-check only, never a
  registry digest.

`program/model-drafts/htdemucs_6s.json` (exact field set, frozen):

```json
{
  "schema_version": 1,
  "draft_for": "program/models.json",
  "model_id": "demucs-htdemucs_6s-5c90dfd2",
  "entry": {
    "url": "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/5c90dfd2-34c22ccb.th",
    "sha256": null,
    "max_bytes": 54996327,
    "expected_bytes_source": "HTTP HEAD 2026-10-07, docs/research/2026-10-07-stems-weights-licence.md",
    "upstream_sha256_prefix_cross_check": "34c22ccb",
    "format": "demucs serialized package (torch.save of klass/args/kwargs/state); loaded only after sha256 verification",
    "license": "Weights: no licence file; maintainer statements limit use to personal/research (facebookresearch/demucs issues 327 and 384). Code MIT does not cover weights. Training data includes MUSDB18-HQ (other-nc).",
    "license_verdict": "admissible_private_comparator",
    "license_conditions": ["personal_research_use_only", "no_redistribution_of_weights_or_real_take_outputs", "outputs_under_ignored_artifacts_v6", "outputs_labelled_estimates", "operator_acknowledgement_before_first_use"],
    "operator_terms_acknowledgement": null,
    "source_commit": "e976d93ecc3865e5757426930257e200846a520a",
    "sources": ["drums", "bass", "other", "vocals", "guitar", "piano"],
    "model_rate_hz": 44100,
    "model_channels": 2,
    "gate_state": "registered_pending_fetch"
  }
}
```

Root fills `sha256` from its own explicit hash-bound fetch and
`operator_terms_acknowledgement` from an explicit operator answer (a receipt
reference string), then commits the `entry` object under `models` in
`program/models.json`. The `sources` order and model rate/channels are the
upstream values as recalled from the Demucs v4 source and must be confirmed
against the pinned package in the runtime lane; a mismatch is a recorded
deviation, not a silent fix.

## 4. Request (closed schema)

The CLI is `python3 scripts/stems_estimate.py estimate --request <file|->` with a
JSON object. The MCP descriptor draft has the same properties. Any extra key,
wrong type or non-finite number refuses `request_invalid`.

| Key | Type | Rule |
| --- | --- | --- |
| `run_dir` | string, 1–4096 | existing directory beneath `artifacts/runs/` or `artifacts/s2/stems_contract/fixtures/`; no `..`, no symlink component |
| `input_role` | enum `denoised`, `source`; default `denoised` | selects `denoised.wav` or `source.wav`, both bound by `manifest.output_sha256` |
| `excerpt_start_seconds` | number ≥ 0 | source-timeline seconds relative to `timeline.audio_start_seconds` |
| `excerpt_end_seconds` | number > start | same timeline |
| `timeout_seconds` | integer 1–900; default 660 | outer deadline; the worker's internal inference deadline is 600 s |

Excerpt length `end - start` must be ≥ 1.0 s (else `request_invalid`) and
≤ 30.0 s (else `excerpt_too_long`). There are **no model knobs**.

Fixed settings, recorded in `runtime_identity.apply_settings`:
- checkpoint `htdemucs_6s` single model, CPU, 2 threads (`OMP/OPENBLAS/MKL`);
- upstream `apply_model` CLI defaults: `shifts=1`, `overlap=0.25`,
  `split=True`, `segment=None` (model default);
- Python `random` and `torch.manual_seed` seeded with `20261007` so the
  shift offset is reproducible;
- deadline 600 s, RSS ceiling 3 GiB.

The `apply_model` defaults are recalled, not verified; the runtime lane confirms
them against the pinned source.

## 5. Refusals (fail closed, typed, first failure wins, never raises past `main`)

The refusal object is
`{schema_version:1, status:"refused", refusal_code, message, model_id, network_used:false, model_acquired:false, default_adoption:false, recovered_original_stem:false}`.
The process prints it on stdout and exits 2.

| Order | Stage | Condition | `refusal_code` |
| --- | --- | --- | --- |
| 1 | request (no I/O) | extra/missing key, wrong type, non-finite, excerpt < 1.0 s, end ≤ start | `request_invalid` |
| 2 | request (no I/O) | excerpt length > 30.0 s | `excerpt_too_long` |
| 3 | registry | `program/models.json` missing, symlinked, > 1 MiB, wrong schema, or no entry for the id | `model_not_registered` |
| 4 | registry | entry `sha256` not 64 lowercase hex (`null` included) | `model_hash_not_registered` |
| 5 | registry | `url` not HTTPS without userinfo, `license` empty, `max_bytes` not int in (0, 2 GiB] | `model_registry_entry_invalid` |
| 6 | registry | `operator_terms_acknowledgement` missing, null or empty (research condition 5) | `model_terms_not_acknowledged` |
| 7 | model file | `models/<id>.bin` missing, symlinked or larger than `max_bytes` | `model_file_missing` |
| 8 | model file | file sha256 ≠ registry | `model_hash_mismatch` |
| 9 | runtime | runtime not configured, not Linux, interpreter outside `artifacts/model-runtime-env/`, identity probe fails or times out (60 s), or `demucs`/`torch` versions not pinned and equal | `runtime_unavailable` (with `runtime_reason` ∈ `not_configured`, `platform_unsupported`, `path_rejected`, `identity_failed`, `not_pinned`) |
| 10 | input | `run_dir` containment/symlink/traversal; manifest missing, > 1 MiB or invalid; input WAV hash ≠ `output_sha256`; `timeline.audio_start_seconds` not finite; `source.sha256` not 64 hex; WAV not mono, not PCM16/24/32/float32, or > 300 s; excerpt end beyond duration | `input_not_admitted` |

Today, with the committed `program/models.json` (no stems entry), every valid
request refuses `model_not_registered`. Runtime configuration is environment
only: `VIDEO_UTILS_STEMS_RUNTIME_PYTHON` (path to the isolated interpreter
prepared by a future root-run runtime lane). The pinned versions are module
constants `DEMUCS_PIN = None`, `TORCH_PIN = None` until that lane qualifies
them; `None` refuses `runtime_unavailable` / `not_pinned`. Mono input is
required so that `estimate_from_mono_mixture: true` is always true.

## 6. Runtime path

1. Validate request (orders 1–2), resolve the model (3–8), the runtime (9) and
   the input (10).
2. Read the excerpt from the manifest-bound WAV as exact frames:
   `start_frame = round(start × R)`, `frame_count = round(end × R) - start_frame`,
   where `R` is the WAV rate. The source-timeline origin from the manifest is
   carried, never defaulted to zero.
3. Sample-rate conversion. If `R == 44100` nothing is resampled (`applied:false`).
   Otherwise FFmpeg (`scripts/media.py` executable resolution, honouring
   `FFMPEG`) converts `R → 44100` with `aresample=44100:resampler=swr` and back
   with `aresample=R:resampler=swr`. Both filter strings are recorded. After
   the return, stems are trimmed or zero-padded to exactly `frame_count` frames.
   `length_adjust_frames` is recorded; |adjust| > 2 frames is an internal failure
   (`status:"failed"`, `failure_code:"round_trip_length_mismatch"`), not a
   refusal.
4. Channel conversion: mono is duplicated to two identical channels for the
   model (`mono_duplicated_to_stereo`); each estimate is returned to mono as the
   mean of the two model channels (`stereo_mean_to_mono`).
5. The model-rate stereo float32 buffer is written as `model_input.wav`. Its
   sha256 is `analysed_input.sha256`.
6. Inference runs in a child process:
   `<runtime python> -I scripts/stems_estimate.py infer --task <task.json>` in a
   fresh lane work directory.
   - The child sets `TORCH_HOME`/`HF_HOME`/`XDG_CACHE_HOME` to an empty lane
     directory and `HTTP(S)_PROXY` to `http://127.0.0.1:9`.
   - It never calls `demucs.pretrained.get_model` or any hub/URL loader. It
     loads only the sha256-verified local file.
   - It tries `torch.load(weights_only=True)` first. If the Demucs package
     format requires full unpickling, the child unpickles only after the parent
     re-verifies sha256 immediately before launch, and records
     `checkpoint_load:"pickle_after_sha256_verify"`. Otherwise it records
     `"weights_only"`.
   - It runs under an owned process group with the deadline and RSS ceiling,
     and writes a resource receipt.
7. Six estimate WAVs `stems/<name>.wav` are written as `pcm_f32le`, mono, at the
   source rate `R` with exactly `frame_count` frames. Their first frame
   corresponds to source-timeline `excerpt_start_seconds`.
8. The parent computes the low-end check and mixture consistency (section 7)
   in the stdlib.

The separator seam is a callable
`separator(stereo_44k: list[list[float]], model: dict, workdir: Path) -> dict[str, list[list[float]]]`,
returning exactly the six source names, each 2 × N at 44.1 kHz. The runtime seam
is `runtime_resolver(root) -> dict`. Tests inject both. The default separator
is the child-process runner above.

## 7. Result (`stems_estimate.json`, schema_version 1, closed key set)

The top-level keys are exactly the ones below. A test asserts set equality.

- `schema_version:1`, `status:"completed"`, `tool:"stems_estimate"`.
- `model_identity{model_id, sha256, registry_sha256, source_url, license_verdict, terms_acknowledgement, checkpoint_load}`.
- `runtime_identity{kind:"isolated_child"|"injected_fake", python, torch|null, demucs|null, platform, host_label, threads:2, seed:20261007, apply_settings{shifts, overlap, split, segment}}`.
- `input_identity{input_role, path_role, input_sha256, run_manifest_sha256, source_sha256, signal_version:"sha256:<input_sha256>", source_rate, source_channels:1, real_take}`.
  `real_take` is false only for a manifest with `source.kind == "generated_fixture"`,
  a generator id and an integer seed (fail closed, as in Beat This).
- `excerpt{source_timeline_origin_seconds, source_start_seconds, source_end_seconds, start_frame, frame_count, rate}`.
- `analysed_input{sha256, rate:44100, channels:2, frames, sample_rate_conversion{input_rate, model_rate:44100, applied, forward_filter|null, return_filter|null, length_adjust_frames}, channel_conversion{to_model:"mono_duplicated_to_stereo", from_model:"stereo_mean_to_mono"}}`.
- `stems[]`, six entries in model order:
  `{name, model_target_label, path, sha256, rate, channels:1, frames, source_start_seconds, source_end_seconds, estimate:true}`.
- `low_end_check` (measured):
  - `band_hz:[20,45]`, `reference_band_hz:[45,120]`;
  - `filter:"rbj_butterworth4_bandpass_cascade"`: 2 high-pass biquads at the
    lower edge and 2 low-pass biquads at the upper edge, Q 0.5412 and 1.3066;
  - `settle_excluded_seconds = min(0.25, 0.25 × excerpt length)`, applied
    identically to every signal;
  - `input{band_energy, reference_band_energy}`;
  - `per_stem{<name>:{band_energy, reference_band_energy, band_ratio_to_input_db|null, band_share_of_stem_sum|null}}`;
  - `guitar_vs_input_band_db|null`, `guitar_plus_bass_vs_input_band_db|null`;
  - `status` ∈ `measured`, `zero_reference`.
  Energies are mean squares over the measured frames at rate `R`, after the
  round trip. `null` appears with a `*_reason` key when the reference is zero.
- `mixture_consistency{residual_vs_input_full_db|null, residual_vs_input_band_db|null}`.
  The residual is (sum of six estimates) − input excerpt (measured).
- `resource_receipt{elapsed_seconds, deadline_seconds:600, rss_ceiling_bytes, max_rss_bytes|null, measurement_seconds}`.
- `privacy`: `"V6_private_real_take_derived"` when `real_take`, else
  `"generated_fixture"`.
- `limitations[]` (section 7.2).
- The unknown/abstain fields of 7.1, flattened at top level.

### 7.1 Unknown and abstain fields (always present, exact values; 17)

| Field | Value |
| --- | --- |
| `estimate_from_mono_mixture` | `true` |
| `recovered_original_stem` | `false` |
| `stem_semantics` | `"model_target_allocation_not_instrument_identity"` |
| `instrument_presence_claim` | `"none"` |
| `separation_accuracy` | `"unknown"` |
| `low_end_preservation_verdict` | `null` |
| `listening_accepted` | `false` |
| `bleed_artifact_review` | `"not_performed"` |
| `default_adoption` | `false` |
| `cleanup_default` | `false` |
| `master_eligible` | `false` |
| `in_room_tone_recreated` | `false` |
| `note_correctness` | `null` |
| `performance_issue` | `null` |
| `expected_rhythm_reference` | `null` |
| `claim_class` | `"model_output_measurement"` |
| `redistribution_permitted` | `false` |

### 7.2 Required limitations

The limitations must state that:
- all six outputs are model allocations of a mono mixture, not recovered
  stems, and labels do not identify instruments;
- low-end numbers are band-energy measurements on estimates. They do not show
  that ~32 Hz content is musically preserved, and listening review is
  separate;
- C1 guitar may be allocated to `bass` and click attacks to `drums`;
- the model was trained on full-band music (MUSDB18-HQ plus undisclosed sets),
  and its behaviour on a heavily distorted nine-string with a box fan is
  unknown;
- the weights are personal/research only, and real-take outputs are private
  (V6) and never redistributed;
- an estimate is never a cleanup, tone or master input by default.

## 8. Preregistration (htdemucs_6s on generated fixtures)

Sealed by this commit. Phase 1 generated no fixture and read no truth. The
held-out suite is generated **only when arm A1 is runnable** (root fetch,
operator acknowledgement and a qualified runtime). Until then the lane records
`blocked_with_receipt`, which is valid completion.

### 8.1 Fixtures: suite `s3-stems-1`

The suite is generated by `stems_estimate.generate_fixture(cohort, seed)`,
which is stdlib only and deterministic (`random.Random(seed)`). Format: 44.1 kHz
(the model rate, so the experiment does not conflate resampling), mono float32,
10.0 s per case.

Components are rendered separately and summed into the mixture: `guitar`, `fan`
and `click`. The synthesis recipe is the same as `MODEL_LANES_S3.md` 7.1,
parameterised by rate:
- tones use the `program/instrument.json` tuning (theoretical A4 = 440),
  additive partials 1–12 below 0.45 × rate, tanh drive 4, 2 ms attack,
  exponential decay τ 0.4 s;
- the palm-mute variant uses τ 60 ms with partials above 8 attenuated 12 dB;
- the fan proxy is one-pole 400 Hz low-passed uniform noise at −42 dBFS RMS;
- the click is a 1 ms 3 kHz Hann burst at −18 dBFS peak on every beat.

Seeds drive the fan noise and ±5 ms note-onset jitter.

| Cohort | Guitar construction (fan and click always present) |
| --- | --- |
| k1-c1-chug | 178 BPM 16th palm-mute chugs on C1 (32.70 Hz), 4 s rest-free, then F1 chugs |
| k2-low-sustain | sustained open C1, F1, Bb1 notes of 1.5 s each (τ 0.4 s), low-string weight and sustain |
| k3-high-legato | Ab3–F4 legato runs (30 ms attacks, onsets 8 dB weaker) over C1 pedal hits every 2 beats at 160 BPM |
| k4-negative | no guitar (truth guitar is digital silence); fan and click only |

Truth is the separate `guitar.wav`, `fan.wav` and `click.wav` plus
`truth/<case>.json`, written mode 0400 under `fixtures/s3-stems-1/truth/`. The
mixture is written as a run-shaped case directory
`fixtures/s3-stems-1/cases/<case>/` with `manifest.json`
(`source.kind:"generated_fixture"`, generator id, seed, `source.sha256`,
`output_sha256`, `timeline.audio_start_seconds:0.0`) and
`denoised.wav = source.wav = mixture`. Prediction code never opens `truth/`.

Seeds:
- Dev seed 4001: smoke tests only, never scored or reported as held-out.
- Held-out seeds 4103 and 4211: 4 cohorts × 2 = **8 held-out cases** (6 guitar,
  2 negative).
- Excluded as consumed elsewhere: 211, 307, 617, 719, 1009, 1301, 1423, 1511,
  1613, 3001, 3101, 3203.

### 8.2 Arms

- **A0 passthrough:** guitar estimate := the mixture excerpt (no separation).
- **A1 htdemucs_6s:** `stems_estimate` with the fixed settings of section 4, on
  the whole 10 s case (excerpt 0–10 s); estimate = the `guitar` output.
- **A1-gb readout (preregistered secondary, same A1 run):** `guitar + bass`.
  This tests where C1 energy went. It is not a separate arm.

No other arm, checkpoint, shift count or setting is added after sealing.

### 8.3 Seal-before-truth protocol

1. Generate held-out mixtures and truth. Hash every WAV and truth file into the
   suite `manifest.json`.
2. Run A0 and A1 on all 8 cases. Write `predictions/<arm>/<case>/` and
   `seal.json` (the sha256 of every prediction file, plus UTC time) **before**
   any truth read. The scorer refuses unless `seal.json` exists, its hashes
   match, and its time precedes the scorer start.
3. Score once. A re-run is allowed only to reproduce bit-identical scores. Any
   change is a new experiment with new seeds, reported separately.

### 8.4 Scoring (stdlib; per case, then medians; every case listed)

Let `g`, `f`, `k` be the truth guitar, fan and click and `e` the estimate. All
values are on the full 10 s, band filters as in section 7.

- **S1 low-band retention** (k1–k3): `10·log10(E₂₀₋₄₅(e) / E₂₀₋₄₅(g))` dB, plus
  the band correlation coefficient ρ(e, g) in 20–45 Hz.
- **S2 SI-SDR** (k1–k3): full band, `e` against `g`, in dB.
- **S3 fan leakage** (k1–k3): least-squares projection of `e` onto `[g, f, k]`.
  Report `10·log10(E(b·f) / E(f))` dB for the fan coefficient `b`, full band and
  20–45 Hz.
- **S4 false allocation** (k4): `10·log10(E(e) / E(mixture))` dB, full band and
  20–45 Hz.
- **Aggregation.** Medians over the 6 guitar cases (S1–S3) and over the 2
  negative cases (S4), with each per-case value listed. Rates are never
  averaged. A zero denominator gives `null` with a reason.
- **Decision rule** (descriptive only, never adoption):
  - "A1 separates without low-band loss on generated fixtures" requires all of:
    median S2(A1) ≥ median S2(A0) + 3 dB; median S1(A1) ≥ −3 dB; median
    full-band S4(A1) ≤ −10 dB.
  - Otherwise the result is "no separation benefit shown on generated
    fixtures".
  - Independently, `low_band_loss_observed` is reported when median S1(A1)
    < −3 dB. It is also reported for the A1-gb readout.
  - Either outcome leaves every default unchanged and makes no real-take claim.
    `default_adoption` remains `false`.

### 8.5 Real-take pass (conditional, measurements only)

- **Input:** the accepted FULLER run
  `artifacts/runs/20261006T041633Z-990aa1bd6737`, `denoised.wav`
  (manifest sha256 `26c9f42c…bfd`, 44.1 kHz mono, 150.96 s).
- **Excerpt:** `[30.0, 60.0)` s, fixed now and not chosen from content. The
  first five seconds of setup sounds are avoided.
- **Prerequisites:** the registered model, the operator terms acknowledgement,
  the qualified runtime, and root confirmation of the V6 private scratch path on
  the run host.
- **Reports:** `low_end_check`, `mixture_consistency` and identities only. There
  is no accuracy and no listening claim. Outputs stay private under ignored
  artifacts.

## 9. Root-owned changes requested (drafts; exact text in the phase-2 handoff receipt)

1. **`program/models.json`:** add `"demucs-htdemucs_6s-5c90dfd2": <entry>` from
   `program/model-drafts/htdemucs_6s.json`, after:
   - root's explicit `just model-prefetch`-style hash-bound fetch, which fills
     `sha256`; the 8-hex prefix `34c22ccb` is a cross-check only;
   - a recorded operator acknowledgement, which fills
     `operator_terms_acknowledgement`.
   Root does not commit the entry with a `null` digest.
2. **`program/tools.json`:** admit the descriptor from
   `program/tool-drafts/stems_estimate.json` as `implementation_status:
   "experimental"` with
   `evidence_kind: "uncalibrated_model_stem_estimates_from_mono_mixture"`.
3. **`scripts/tool_api.py`:**
   - add `'stems_estimate': 0` to `TYPED_REFUSAL_TOOLS`;
   - add `'stems_estimate'` to `TRAVERSAL_GUARDED_RUN_TOOLS`;
   - dispatch to `scripts/stems_estimate.py estimate --request -` under the
     owned-process-group deadline.
   `scripts/mcp_server.py` catalog follows `tools.json`.
4. **`just/workflow.just`:** a recipe
   `stems-estimate run_dir start end input_role="denoised"`, which calls the
   worker with a JSON request.
5. **Skill path:** root may rename `.agents/skills/stems-estimate/` to the
   `guitar-*` convention at admission. The descriptor `skill` field follows the
   rename.
6. **Runtime lane (separate):** pin `demucs` and `torch` on honey (Linux CPU),
   confirm the `sources` order, model rate and `apply_model` defaults, and set
   `DEMUCS_PIN`/`TORCH_PIN`.
7. **`program/linear.json`:** no change from the lane.

## 10. Completion metrics (denominators and claim classes)

| # | Metric | Denominator | Claim class |
| --- | --- | --- | --- |
| M1 | Refusal coverage: each code of section 5 has a passing test (`request_invalid`, `excerpt_too_long`, `model_not_registered`, `model_hash_not_registered`, `model_registry_entry_invalid`, `model_terms_not_acknowledged`, `model_file_missing`, `model_hash_mismatch`, `runtime_unavailable`, `input_not_admitted`), with network patched to raise | 10 codes | test measurement |
| M2 | Refusal precedence: a request violating orders *i* and *j* (i < j) returns *i*, for adjacent pairs | 9 pairs | test measurement |
| M3 | Today behaviour: the committed `program/models.json` makes a valid request refuse `model_not_registered`, with nothing written | 1 case | test measurement |
| M4 | Import hygiene: after import and after every refusal, `torch`, `torchaudio`, `demucs` and `numpy` are absent from `sys.modules`; `socket.socket` and `urllib.request.urlopen` are never called | 4 modules, 2 network entry points | test measurement |
| M5 | Fake-separator end-to-end: result key set equals section 7 exactly; all 17 unknown fields present at exact values; 6 stems with sha256, rate, frame count | 1 schema, 17 fields, 6 stems | test measurement |
| M6 | Low-end accounting on a 32.70 Hz + 261.6 Hz fixture with three fake separators: identity (guitar = input, guitar_vs_input_band_db within ±0.2 dB of 0); low-to-bass (all 32.7 Hz to `bass`: guitar ≤ −40 dB, bass share ≥ 0.99); −6 dB guitar (within ±0.2 dB of −6.02) | 3 cases | test measurement |
| M7 | Sample-rate round trip with identity separator: (a) 48 kHz input through FFmpeg 48k→44.1k→48k has exact `frame_count`, cross-correlation lag 0 ± 1 sample, 20–45 Hz and 1 kHz energy ratios within ±0.2 dB, and filters recorded; (b) 44.1 kHz input has `applied:false` and bit-exact float32 passthrough | 2 cases | test measurement |
| M8 | Source timeline: with a nonzero excerpt start and manifest origins 0.0 and 1.25 s, the excerpt frame mapping and stem `source_start_seconds` are exact; identity-separator samples equal the input excerpt | 2 cases | test measurement |
| M9 | No writes into `run_dir`; the run manifest and WAV hashes are unchanged; outputs only beneath `artifacts/s2/stems_contract/` | every end-to-end test | test measurement |
| M10 | The descriptor draft passes `tool_api.validate_schema` (imported read-only), has the 12 keys of an admitted descriptor, and has `additionalProperties:false` | 1 descriptor | test measurement |
| M11 | The registry draft has the frozen field set of section 3, `sha256:null`, `max_bytes` 54,996,327, and `gate_state:"registered_pending_fetch"` | 1 entry, 15 entry fields | test measurement |
| M12 | SKILL.md has the sections intent, knobs, dependencies, research, iteration, evidence and refusals, and links the research doc | 7 sections | documentary |
| M13 | Fixture generator determinism (dev seed 4001 → identical sha256 twice); truth/prediction directory separation; seal refuses a tampered prediction | 3 behaviours | test measurement |
| M14 | Preregistered experiment (section 8) run with root's fetch and runtime, **or** `blocked_with_receipt` naming the missing prerequisite | 8 held-out cases | measurement on generated fixtures |
| M15 | Conditional real-take pass (8.5) **or** blocked receipt | 1 excerpt, measurements only | measurement without truth (private) |

No metric claims separation accuracy on the real take, recovered stems,
instrument presence, low-end musical preservation, listening acceptance or note
correctness. Experimental non-improvement, or a blocked M14/M15 with a receipt,
is valid completion. A test skipped for missing FFmpeg counts as **not met**
for M7.

## 11. Exact test protocol

Run from the worktree root. There is no network. FFmpeg is needed only for M7a:

```sh
export FFMPEG=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg
export FFPROBE=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffprobe
PYTHONPATH=tests python3 -m unittest test_stems_estimate -v
PYTHONPATH=tests python3 -m unittest test_beat_this_compare test_media -v   # directly affected readers (WAV/media helpers reused), unchanged
```

Fixtures in `tests/test_stems_estimate.py` (all in `tempfile` roots; nothing
under the real `artifacts/`):
- a temporary repository root with `program/models.json` variants: absent,
  wrong schema, null sha256, bad URL, no acknowledgement, and valid. The valid
  variant has a random-bytes `models/demucs-htdemucs_6s-5c90dfd2.bin` and its
  own sha256.
- run-shaped directories under `<tmp>/artifacts/runs/<id>/` with a manifest
  binding `denoised.wav`/`source.wav`. One is real-take shaped (no
  `generated_fixture`). One is a generated fixture. A stereo WAV is used for
  `input_not_admitted`, and a hash-mismatched WAV for the binding check.
- WAVs written in-process with stdlib `wave`/`struct`:
  - 2.0 s of 32.70 Hz + 261.6 Hz at 44.1 kHz;
  - the same at 48 kHz for M7a;
  - PCM16 and float32 variants.
- fake runtime: `{'kind':'injected_fake', 'python':..., 'torch':None, 'demucs':None, ...}`.
- fake separators: identity-to-guitar, low-to-bass (a stdlib 45 Hz biquad
  split), and a guitar −6 dB scaler. Each returns six 2 × N buffers.
- `socket.socket` and `urllib.request.urlopen` are patched to raise in every
  test class. `sys.modules` is checked for torch/torchaudio/demucs/numpy.
- `generate_fixture("k1-c1-chug", 4001, duration=2.0)` for determinism and
  directory separation only.

Heavy numerics are limited to one job at a time with explicit timeouts. Real A1
inference runs only on honey after root's fetch, the acknowledgement and the
runtime lane.

## 12. Receipts

The receipts are under `docs/agent-notes/sprints/20261007-s3/`:
- `stems_contract-contract-freeze.json` (this phase);
- `stems_contract-implementation.json`;
- `stems_contract-tests.json`;
- `stems_contract-experiment.json` or a blocked receipt;
- `stems_contract-handoff.json`, which carries the exact root-owned change
  text of section 9.

Each cites R-N13 and records file hashes. Measurements, inferences and
unverified listening claims stay in distinct fields.

## 13. Phase-2 implementation notes (additive; sections 1-12 unchanged)

Recorded at implementation (2026-10-07). Each note is an interpretation of an
open point or a declared deviation. None of them changes a refusal order,
fixed setting, preregistered seed, arm, metric or decision rule.

**Interfaces**
- **Timeline.** `excerpt_*_seconds` are seconds from
  `timeline.audio_start_seconds` (WAV-relative):
  `start_frame = round(start × R)`. The reported `source_start_seconds` /
  `source_end_seconds` of the excerpt and of every stem are
  `origin + frame / R`, so the origin is always carried.
- **CLI.** It adds `--request-json <text>` beside `--request <file|->`, with
  the same closed schema. `tool_api` runs workers with stdin `DEVNULL`, as in
  `guitar_noul_decide`.
- **Refusal object.** It carries one additive key, `runtime_reason`, which is
  `null` except for `runtime_unavailable`.
- **Runtime reasons** are checked in this order:
  1. `not_configured`;
  2. `platform_unsupported`;
  3. `path_rejected`: not absolute, `..`, outside `artifacts/model-runtime-env/`,
     any symlink component (the interpreter file included), or not executable;
  4. `not_pinned`: pins are `None`, checked before any probe;
  5. `identity_failed`: the probe fails or exceeds its 60 s timeout;
  6. `not_pinned`: probed versions differ from the pins.

  The probe reads package metadata only (`importlib.metadata`) and never imports
  torch. A symlinked venv interpreter is rejected; the runtime lane provides a
  real interpreter file or asks root to change the rule.
- **Failure codes** after admission (`status:"failed"`, exit 1, `failure.json`
  in the work directory):
  - `round_trip_length_mismatch`;
  - `separator_output_invalid`;
  - `inference_failed`;
  - `input_or_model_changed`;
  - `model_changed` (pre-launch recheck);
  - `analysed_input_mismatch`;
  - `separator_unavailable`;
  - `resampler_unavailable` / `resampler_failed`;
  - `output_path_rejected`;
  - `internal_error`.
- **Unreadable files.** An `OSError` while hashing the model maps to
  `model_file_missing`. An `OSError`/`ValueError` while reading the input maps
  to `input_not_admitted`. A NUL in `run_dir` is `request_invalid`.

**Measurements**
- **`low_end_check` additive inner keys:**
  - `biquad_q`, `rate_hz`, `measured_frames` and `claim_class`;
  - every `*_reason` key, always present and `null` when a value is measured.

  The reason values are `zero_input_band_energy`, `zero_stem_band_energy`,
  `zero_guitar_band_energy`, `zero_guitar_plus_bass_band_energy` and
  `zero_stem_band_sum`.
- **`mixture_consistency`** is measured on the same frames as the low-end check,
  after settle exclusion. It adds `residual_definition`, `claim_class` and the
  reason keys `zero_input_energy`, `zero_residual_energy` and
  `zero_residual_band_energy`.
- **`runtime_identity.python`** is the child's Python version once real inference
  has run, as in Beat This. For the injected fake it is the fake's label.
  `model_identity.checkpoint_load` is `"not_loaded_injected_fake"` for the fake.
- **Child normalisation.** The child applies the upstream separate-CLI
  normalisation (mixture mean/std, with std 0 guarded to 1) around
  `apply_model`. This is recalled, not verified. It is recorded in the child's
  `inference.json`. The runtime lane confirms it with the `sources` order, the
  model rate and the `apply_model` defaults.

**Tests (section 11)**
- **M6 low-to-bass fake.** An order-4 45 Hz split cannot reach −40 dB at
  32.70 Hz: the Butterworth-4 high-pass at 45 Hz gives about −11 dB. The fake
  therefore cascades 12 RBJ high-pass biquads at 45 Hz (Q 0.7071) for `guitar`,
  and `bass = input − guitar`.
- **M7a fixture.** The 48 kHz fixture adds a 1 kHz component (amplitude 0.1) to
  32.70 Hz + 261.6 Hz, so that the contract's 1 kHz energy ratio is measurable.
- **Measured swr round trip** (FFmpeg 8.1.2, 2 s, 48 kHz → 44.1 kHz → 48 kHz):
  - 88,200 / 96,000 frames;
  - cross-correlation peak at lag 0;
  - 20–45 Hz −0.0001 dB and 800–1250 Hz +0.0001 dB;
  - maximum sample error 1.0e-5 away from the edges.

**Section 8.1 choices the contract left open**
- Grid start t0 = 0.25 s.
- Click tempo: k2 at 120 BPM (1.5 s notes = 3 beats); k4 at 178 BPM.
- The k3 legato run is the fixed cycle Ab3 Bb3 C4 Db4 Eb4 F4 Eb4 Db4 C4 Bb3 in
  sixteenths. Seeds drive only the fan and the jitter.
- Jitter is Gaussian with σ 2 ms, clipped to ±5 ms. Legato τ is 0.4 s.
- Layout:
  - truth: `truth/<case>/{guitar,fan,click}.wav` and `truth/<case>.json`, each
    mode 0400;
  - predictions: `predictions/<arm>/<case>/{guitar.wav[, bass.wav], record.json}`.

**Scoring**
- **Settle exclusion.** Band-filtered metrics (S1, the band parts of S3 and S4)
  exclude the same settle window as section 7. Full-band metrics use all
  frames.
- **Infinities.** Infinite values from zero energies are reported as
  `value:null` with the reason `minus_infinity_zero_numerator_energy` or
  `plus_infinity_zero_error_energy`. They take part in the medians and the
  decision as ±∞. Undefined values (zero reference) are excluded, with
  `n_defined` recorded.
- **Seal checks.** The scorer verifies the seal (it exists, predates the scorer,
  the file set is equal and the hashes match) before it refuses dev suites, so
  tampering is reported first. Dev suites are never scored.
- **Held-out generation** calls the registry and default runtime resolution
  first. It refuses (for example `model_not_registered`) and writes nothing
  until arm A1 is runnable.
