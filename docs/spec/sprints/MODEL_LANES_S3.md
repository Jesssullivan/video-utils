# S3 model_lanes lane contract (phase 1 freeze and preregistration)

Lane `model_lanes`, sprint `20261007-s3`, Linear TIN-5721 (parent TIN-5717;
related TIN-5554, TIN-5619). Branch `sprint/20261007-s3/model_lanes`, worktree
`.local/sprint3/model_lanes`. Root signs the merge. Authority: the operator
decision row "Model lanes" in `docs/spec/sprints/20261007-S3.md`, the repository
AGENTS.md, the V6 ruling in `docs/agent-notes/2026-10-07-s2-operator-rulings.md`,
and R-HOOK-CONVERGENCE-20261004 (R-N11/R-N12/R-N13).

This file is the lane's frozen contract **and** its preregistration. The commit
that adds it seals the fixtures, seeds, arms, scoring rules and decision rule in
section 7. Phase 1 ran no numerics, downloaded nothing, and did not read any
generated truth. The only external evidence read in phase 1 was the CPJKU
`beat_this` README (2026-10-07; it states "The code and the published model
weights are released under the MIT license" and names the checkpoints
`final0..2`, `small0..2`, `single_final0..2` and `fold0..7`, hosted on the JKU
Nextcloud share `https://cloud.cp.jku.at/index.php/s/7ik4RrBKTS273gp`, with
automatic download in the inference code) and the TIN-5619 description. Both are
recorded here as inputs. The research documents verify these facts against
primary sources; this file does not.

## 1. Scope

There are three deliverables. None of them changes a default detector, profile,
master, catalog entry or registry.

1. **Beat This comparator (never a default).**
   - `docs/research/BEAT_THIS_QUALIFICATION.md` is written from primary sources:
     the repo, the pinned commit/tag, the checkpoint URL, the code and weights
     licence, checkpoint byte sizes, runtime dependencies, input rate and frame
     rate. No weights are downloaded.
   - The registry entry text for exactly one checkpoint (`final0`, the upstream
     default) goes to root as a requested change (section 8). Its `sha256` is
     marked `TO_BE_FILLED_BY_ROOT_HASH_BOUND_FETCH`.
   - `scripts/beat_this_runtime_setup.py` is an isolated pinned runtime modelled
     on `basic_pitch_runtime_setup.py`. It targets Linux CPU on honey through
     the flake `ml` shell (torch/torchaudio from nixpkgs). The Beat This package
     and the pure-Python dependencies the ml shell lacks (`einops`,
     `rotary-embedding-torch`, `soxr`, `tqdm`) are pinned by sha256 in a lock
     constant inside the script. Installation is offline and `--no-deps`. It
     never acquires a model, and `--check` is read-only.
   - `scripts/beat_this_compare.py` consumes an already-installed,
     registry-verified checkpoint through that runtime. It reports beats,
     downbeats, `half_double_ratio_vs_click_grid`, and F-measure at 70 ms on
     **generated truth only**. `meter_claim` is always `"none"`.
2. **guitar_noul gateway client (TIN-5619).** `scripts/guitar_noul_client.py`
   implements the closed contract as a client against a configurable gateway
   URL.
   - With the URL unset, it returns the typed refusal `gateway_not_configured`.
   - Every per-window decision is a detector hypothesis, never a label.
   - Windows from a real take are sent only when the operator configuration
     allows it (V6).
   - Tests use an injected mock transport. No server is started and there are
     no sockets.
3. **Stems weights licence qualification.** `docs/research/2026-10-07-stems-weights-licence.md`
   qualifies Demucs v4 (`htdemucs`, `htdemucs_ft`, `htdemucs_6s`) and
   BS/Mel-Band RoFormer checkpoints from primary sources, with access dates. It
   recommends which checkpoint, if any, is admissible. Nothing is downloaded.

Skill drafts `.agents/skills/guitar-beat-this/SKILL.md` and
`.agents/skills/guitar-noul/SKILL.md` and the tool descriptor drafts are handed
to root. Tool admission (catalog, MCP, `program/tools.json`) is root-owned.

Out of scope:
- meter, time-signature or bar-line claims
- missed/extra/wrong-note claims and note correctness
- performance grading
- default adoption of any model output
- stem extraction runs
- model or wheel downloads by the lane
- deploying or calling the real models.xoxd.ai gateway
- listening acceptance

## 2. Owned files

| File | Change |
| --- | --- |
| `scripts/beat_this_compare.py` | new experimental comparator plus the deterministic fixture generator (section 7) |
| `scripts/beat_this_runtime_setup.py` | new isolated Linux CPU runtime setup/check; embedded wheel lock |
| `scripts/guitar_noul_client.py` | new TIN-5619 client |
| `tests/test_beat_this_compare.py` | new; stub model, refusal, scoring and no-network tests |
| `tests/test_guitar_noul_client.py` | new; mocked-gateway tests |
| `docs/research/BEAT_THIS_QUALIFICATION.md` | new research |
| `docs/research/2026-10-07-stems-weights-licence.md` | new research |
| `docs/spec/sprints/MODEL_LANES_S3.md` | this contract |
| `.agents/skills/guitar-beat-this/SKILL.md`, `.agents/skills/guitar-noul/SKILL.md` | new skill drafts |
| `docs/agent-notes/sprints/20261007-s3/model_lanes-*.json` | dated receipts |

Generated outputs go only under `artifacts/s2/model_lanes/` (gitignored), as the
lane rules require. Accepted runs under `artifacts/runs/*`, the V2 bank under
`artifacts/s2/phrase_anchor_riff/` and the original take are read-only.

## 3. Beat This contracts

### 3.1 Model resolution and refusals (fail closed, no network)

The comparator accepts only `model_id = "cpjku-beat-this-final0"`. Resolution
runs in this order, and the first failure returns a typed refusal object
(`status: "refused"`, `refusal_code`, `message`). It never raises past `main`
and never falls back:

| Order | Condition | `refusal_code` |
| --- | --- | --- |
| 1 | `program/models.json` missing, has the wrong schema, or has no entry for the id | `model_not_registered` |
| 2 | Entry `sha256` is not 64 lowercase hex (including the placeholder) | `model_hash_not_registered` |
| 3 | Entry `license`, `max_bytes` or `url` is missing or invalid | `model_registry_entry_invalid` |
| 4 | `models/<id>.bin` is missing, a symlink, or larger than `max_bytes` | `model_file_missing` |
| 5 | The file's sha256 differs from the registry | `model_hash_mismatch` |
| 6 | The isolated runtime is missing or fails its identity check | `runtime_not_qualified` |
| 7 | The platform is not Linux (the inference path only) | `platform_unsupported` |
| 8 | Input is not a verified run `denoised.wav` / fixture WAV, exceeds 300 s, or has a symlink/traversal | `input_rejected` |

Inside the isolated runtime, the checkpoint is loaded with
`torch.load(..., map_location="cpu", weights_only=True)`. The upstream
auto-download path is never called: the code passes a local checkpoint path,
`TORCH_HOME` and `HF_HOME` point at an empty lane directory, and
`HTTP(S)_PROXY` points at an unroutable address.

Other runtime settings:
- CPU only, `float16` off, DBN off (`madmom` is not installed or qualified).
- `OMP/OPENBLAS/MKL_NUM_THREADS=2`.
- 600 s deadline, 2 GiB RSS ceiling, with a resource receipt in the style of
  `run_owned`.

### 3.2 Output (`beat_this_comparison.json`, schema_version 1)

Required keys:
- `model_identity{model_id, sha256, checkpoint:"final0", source_url, license, registry_sha256}`
- `runtime_identity{lock_sha256, python, torch, beat_this_version, platform, host_label}`
- `input_identity{path_role, sha256, run_manifest_sha256|null, signal_version, analysis_rate:22050, resampling:"soxr_in_upstream_preprocess", source_timeline_origin_seconds}`
- `beats[]` and `downbeats[]`. Each event has `{model_seconds, source_timeline_seconds}`.
- `beat_count`, `downbeat_count`, `median_ibi_seconds|null`,
  `ibi_tempo_bpm|null` (60/median IBI, a measurement on model output).
- `half_double_ratio_vs_click_grid`:
  - `{click_grid_source, click_grid_period_seconds|null, ratio|null, nearest_relation|null, relative_error|null, status}`
  - `ratio = click_grid_period_seconds / median_ibi_seconds`. This is the Beat
    This tempo divided by the click-grid tempo.
  - `nearest_relation` ∈ {`1/3`,`1/2`,`2/3`,`1`,`3/2`,`2`,`3`}, chosen only when
    the relative error is ≤ 0.04. Otherwise it is `unrelated`.
  - `status` ∈ {`measured`, `no_click_grid`, `insufficient_beats`}.
  - The click grid is `rhythm.analyze()` `click_grid` from the same analysed
    input with default settings. Generated fixtures also report the ratio
    against the construction click period.
- `generated_truth_scores|null`, filled only for generated fixtures
  (section 7.4). Real takes always carry `null` with
  `generated_truth_scores_reason:"no_generated_truth"`.
- Unknown and abstain fields, always present with these exact values:
  - `meter_claim:"none"`, `time_signature:null`
  - `downbeat_semantics:"model_hypothesis_not_bar_line"`
  - `tempo_identity:"unknown"`
  - `physical_capture_latency:"uncalibrated"`
  - `real_take_accuracy:"unknown"`
  - `note_correctness:null`, `performance_issue:null`,
    `expected_rhythm_reference:null`
  - `listening_accepted:false`, `default_adoption:false`
  - `claim_class:"model_output_measurement"`
  - `confidence_kind:"uncalibrated_model_activation"`
- `limitations[]`. It must state that:
  - beats from a mono mixture with an in-room click are model hypotheses;
  - downbeat spacing does not establish meter;
  - half/double relations are arithmetic on outputs, not an identification of
    intended tempo.

### 3.3 Runtime setup

- `beat_this_runtime_setup.py --check` is read-only. It verifies the embedded
  lock sha256, the installed member hashes, `include-system-site-packages`
  (true here only for the ml-shell torch, recorded explicitly), and imported
  versions.
- `--python <ml-shell python>` installs offline from verified wheels into
  `artifacts/model-runtime-env/beat-this-<version>-linux/`.
- On a non-Linux host it refuses with `platform_unsupported`.
- Wheel fetches, when root runs setup, are restricted to `files.pythonhosted.org`
  (and `codeload.github.com` only if Beat This is pinned as a commit archive).
  They are hash-checked before install, and redirects are checked as in the
  Basic Pitch setup.
- The lock is a constant in the owned script because `program/` is root-owned.
  Root may move it later.

## 4. guitar_noul client contract (TIN-5619)

### 4.1 Input (closed; extra keys refuse `input_schema_invalid`)

`{run_dir, windows:[{source_start_s, source_end_s}], timeout_seconds}`

- `run_dir` is an existing directory beneath `artifacts/runs/` or
  `artifacts/s2/model_lanes/fixtures/`, with no symlink or traversal and a
  regular `manifest.json` ≤ 1 MiB.
- `windows` holds 1–64 windows. Each has finite values with
  0 ≤ start < end ≤ the manifest duration and a length of 0.25–30 s. Windows
  must not overlap. Violations refuse with `window_invalid`.
- `timeout_seconds` is an integer 1–120 and is the overall deadline.

### 4.2 Configuration (environment only; never caller arguments)

- `VIDEO_UTILS_GUITAR_NOUL_GATEWAY`. When unset or empty, the client refuses
  with `gateway_not_configured` before any I/O beyond input validation. The URL
  must be `https`, have no userinfo, port 443 or none, and a host equal to
  `models.xoxd.ai` or ending in `.ts.net`. Anything else refuses with
  `gateway_url_rejected`.
- `VIDEO_UTILS_GUITAR_NOUL_ALLOW_REAL_TAKE`. Only the exact value
  `v6-private-operator-lab-host` permits real-take windows.

**Real-take test.** A run is "synthetic" only when its manifest declares
`source.kind == "generated_fixture"` with a generator id and seed. Every other
run, including all `artifacts/runs/*`, is treated as a real take (fail closed).
Without the allow value, a real take refuses with `real_take_not_permitted`, and
the test asserts that the transport is never invoked.

**Gateway assumptions** (documented, not verified):
- The gateway is tailnet-only behind tsidp and Jess-only. It is not deployed;
  serving waits on TIN-5590 parity, around 2026-10-10.
- The client holds no credentials, tokens or cookies. Identity comes from the
  tailnet.
- HTTP 401/403 maps to `gateway_auth_refused`. Connection errors map to
  `gateway_unreachable`. Neither is retried more than once.

### 4.3 Wire request (provisional, unratified)

TIN-5619 fixes only the video-utils input and the per-window output. The wire
format is drafted here and recorded as `gateway_wire_schema_ratified:false`:

- The client posts one JSON request per call:
  `{contract:"tin-5619-v0", source_sha256, signal_version, windows:[{index, source_start_s, source_end_s, payload_kind:"pcm16_wav_mono_16k_b64", payload}]}`.
- Payload extraction reads only the manifest-verified `denoised.wav` excerpt. It
  is bounded to 30 s per window and 8 MiB per request.
- TIN-5619's earlier sentence ("no real-take audio or features leave
  video-utils") is superseded only to the extent of the later V6 ruling, which
  allows operator-controlled lab hosts. The client therefore keeps that sentence
  as the default (refuse), and the allow variable is the explicit operator
  switch. Root/peer ratification of the payload kind is an open item.

### 4.4 Output (`guitar_noul_decisions.json`, schema_version 1)

- Per window:
  `{index, source_start_s, source_end_s, decision:{label|null}, abstain:bool, abstain_reason|null, confidence_label|null, model_identity:{gguf_sha256, catalog_name}|null}`.
- The client adds these fixed fields to every window:
  - `claim_class:"detector_hypothesis"`
  - `authorship:"detector:guitar_noul"`
  - `is_label:false`, `user_reported:false`
  - `note_correctness:null`, `performance_issue:null`
  - `label_vocabulary_ratified:false`
  - `confidence_kind:"gateway_reported_uncalibrated"`
- Response validation. An invalid response gives the window `abstain:true`,
  `abstain_reason:"gateway_response_invalid"`, and keeps the raw-response
  sha256:
  - `gguf_sha256` must be 64 lowercase hex.
  - `catalog_name` must match
    `^xoxd/rune-26b-a4b-v3-xoruby-[a-z0-9][a-z0-9._-]{0,63}-(\d{8}|\d{4}-\d{2}-\d{2})$`.
  - `label` must be 1–64 chars of `[a-z0-9_.:-]`.
  - Exactly one of `label` and `abstain` must be set.
- A per-window deadline gives `abstain_reason:"timeout"`. Windows the gateway
  omits give `abstain_reason:"missing_from_response"`.
- Gateway labels are opaque strings. They are never mapped to annotation kinds,
  flags, review badges or user labels.
- Top level:
  - `gateway{url_host, configured:true}`, `real_take:bool`,
    `real_take_permission:"v6-private-operator-lab-host"|null`
  - `transport_receipt{attempts, elapsed_seconds, http_status|null}`
  - `privacy:"V6_private_real_take_derived"` when `real_take`
- Output is written to stdout or to `--out` beneath
  `artifacts/s2/model_lanes/`. It is never written into `run_dir`.

## 5. Stems licence qualification contract

For each candidate the document records:
- the exact checkpoint name and URL;
- the hosting page;
- the licence text quoted verbatim with URL and access date;
- the code licence, kept separate;
- the training-data statement if the source gives one;
- the byte size if listed.

Candidates:
- Demucs v4: `htdemucs`, `htdemucs_ft`, `htdemucs_6s`, from the facebookresearch
  and adefossez repos and their checkpoint hosting.
- BS-RoFormer / Mel-Band RoFormer: the lucidrains code, plus ZFTurbo MSST
  release checkpoints and Kimberley Jensen weights. Only checkpoints with a
  guitar or "other" stem are considered.

Each candidate gets one verdict from: `admissible_private_comparator`,
`hold_unresolved_terms`, `excluded`. Code MIT is never inferred to cover
weights. The recommendation may be "none admissible", which is valid
completion. Any admissible pick still needs root's hash-bound registry entry.
Any later stem output is an estimate from a mono mixture, never a recovered
stem.

## 6. Completion metrics (denominators and claim classes)

| # | Metric | Denominator | Claim class |
| --- | --- | --- | --- |
| M1 | Beat This research facts cited to primary URLs with access date: licence (code and weights separately), checkpoint URL, checkpoint bytes, runtime deps, rates | 6 required fact groups | documentary |
| M2 | Registry entry text handed to root with placeholder sha256, max_bytes (from the published size or a stated upper bound), licence, source commit | 1 entry | documentary |
| M3 | Comparator refusal coverage: every row of table 3.1 has a passing test, with no network (socket and urlopen patched to raise) | 8 refusal codes | test measurement |
| M4 | Stub-model end-to-end: beats, downbeats, ratio and F70 computed from a stub runner, with every unknown field of 3.2 present at its exact value | 1 schema, 15 unknown fields | test measurement |
| M5 | F70 scorer correctness against hand cases (perfect, ±69/±71 ms boundary, duplicates, empty truth or prediction → null with reason) | 6 hand cases | test measurement |
| M6 | half/double classifier on constructed ratios (each of the 7 relations, ±3 %/±5 % boundary, no grid) | 9 cases | test measurement |
| M7 | Runtime setup: lock self-hash check, refusal on non-Linux, `--check` performs no download or install | 3 behaviours | test measurement |
| M8 | guitar_noul: each refusal code (`input_schema_invalid`, `window_invalid`, `gateway_not_configured`, `gateway_url_rejected`, `real_take_not_permitted`, `gateway_auth_refused`, `gateway_unreachable`) plus window abstains (`gateway_response_invalid`, `timeout`, `missing_from_response`) with transport-call assertions | 10 outcomes | test measurement |
| M9 | guitar_noul: every emitted window carries `claim_class:"detector_hypothesis"`, `is_label:false`; no file written under `run_dir` | all windows in the tests | test measurement |
| M10 | Stems: candidates qualified with dated quotes; verdict per candidate | ≥ 5 checkpoints | documentary |
| M11 | Preregistered experiment (section 7) run on honey **or** a `blocked_with_receipt` stating which prerequisite is missing (root fetch, runtime, honey placement) | 16 held-out cases | measurement on generated fixtures |
| M12 | Real-take Beat This pass on the accepted FULLER run, only if root confirms an approved V6 private scratch path on honey | 1 take (counts and ratio only, no F) | measurement without truth (private) |

No metric claims real-take beat accuracy, intended tempo, meter, or musical
correctness. Experimental non-improvement, or a blocked M11/M12 with a receipt,
is valid completion.

## 7. Preregistration (Beat This on generated fixtures)

Sealed by this commit. Phase 1 generated no fixture and read no truth.

### 7.1 Fixtures: suite `s3-beat-1`

The suite is generated by `beat_this_compare.generate_fixture(cohort, seed)`,
which is stdlib only and deterministic (`random.Random(seed)`). Format: 48 kHz
mono pcm16, 30 s per case.

**Tones** use the project tuning from `program/instrument.json` (C1 32.70 Hz
through F4, theoretical A4=440 frequencies):
- additive partials 1–12
- tanh saturation, drive 4
- 2 ms attack and exponential decay
- palm-mute variant: decay τ 60 ms, partials above 8 attenuated 12 dB

**Background** is a fan proxy: one-pole low-passed noise at −42 dBFS RMS. **The
click** is a 1 ms 3 kHz burst at −18 dBFS on every truth beat, where the cohort
has a click.

**Truth** (beats, downbeats, click times) is written to a separate
`truth/<case>.json`. Prediction code never reads it.

| Cohort | Construction | Click | Truth beats |
| --- | --- | --- | --- |
| c1-chug178 | 178 BPM, 16th palm-mute chugs on C1/F1, 4-beat groups | yes | quarter notes, downbeat every 4 |
| c2-halftime89 | 89 BPM half-time accents with 16th chugs at 178-grid density | yes | 89 BPM quarters, downbeat every 4 |
| c3-odd7 | 7/8 eighths at 300 eighths/min grouped 2+2+3, accents on group starts | yes | group starts (uneven beats), downbeat every 7 eighths |
| c4-drift | 178→172 BPM linear tempo drift (wind-down model), 8th chugs | yes | drifting quarters, downbeat every 4 |
| c5-rests | c1 with two 2-bar rests (fan only, click continues) | yes | quarters including rests |
| c6-legato | 160 BPM legato/sweep runs: 30 ms soft attacks, 8 dB weaker onsets, Ab3–F4 | yes | quarters, downbeat every 4 |
| c7-noclick | c1 construction without the click | no | quarters, downbeat every 4 |
| c8-negative | fan proxy plus a sustained C1 drone with slow amplitude swells, no pulse | no | **empty** (scored as false beats per minute) |

**Seeds:**
- Dev seed 3001. It is used only for runtime smoke tests, never scored, never
  reported as held-out.
- Held-out seeds 3101 and 3203. That gives 8 cohorts × 2 = **16 held-out
  cases**.
- Seeds excluded as already consumed elsewhere: 211, 307, 617, 719, 1009, 1301,
  1423, 1511, 1613.

### 7.2 Arms

- **A0 baseline:** `rhythm.analyze()` with default settings, unchanged. Its
  beat estimate is the positions of the fitted `click_grid` when non-null.
  Otherwise it is the `selected_periodicity` period, phase-anchored at the first
  high-frequency peak. If neither exists, it predicts no beats. A0 makes no
  downbeat predictions (scored `null`, "arm_has_no_downbeats").
- **A1 Beat This:** checkpoint `final0`, CPU, DBN off, float16 off, upstream
  default postprocessing. There are no tunable knobs, and none will be changed.

No other arm is added after sealing. DBN, `small0` and other folds stay out of
this experiment.

### 7.3 Seal-before-truth protocol

1. Generate held-out audio and truth. Hash every WAV and truth file into
   `manifest.json`. Truth files are mode 0400 and the prediction step never
   opens them.
2. Run A0 and A1 on all 16 cases. Write `predictions/<arm>/<case>.json` and a
   global `seal.json` (sha256 of every prediction file plus UTC time) **before**
   any truth read. The scorer refuses unless `seal.json` exists, its hashes
   match, and its time precedes the scorer start.
3. Score once. Re-running after the scores are seen is allowed only to
   reproduce bit-identical results. Any setting change after scoring is a new
   experiment with new seeds and is reported separately.

### 7.4 Scoring

- **Matching.** `benchmark.event_metrics_v2(truth, predicted, tolerance=0.07)`
  gives an ordered one-to-one maximum-cardinality matching.
- **Beat F70.** Per arm, sum TP, predicted count and truth count over the
  cases, then compute pooled P = ΣTP/Σpred, R = ΣTP/Σtruth, F = 2PR/(P+R). It is
  reported overall (c1–c7, 14 cases) and per cohort (2 cases each). Rates are
  never averaged. When a denominator is zero the value is `null` with a reason.
- **Downbeat F70.** Same rule, A1 only.
- **Negative cohort c8.** False beats per minute are Σpredicted / Σminutes over
  2 cases (1.0 minute total).
- **Half/double.** For each case, report `nearest_relation` of the arm's median
  IBI against (a) the construction click period and (b) A0's click grid. Report
  counts per relation over 14 cases. c3 uses the median truth IBI.
- **Decision rule** (descriptive only, never adoption): "A1 better on
  generated fixtures" requires pooled beat F70(A1) ≥ F70(A0) + 0.05 on c1–c7
  **and** c8 false beats/min(A1) ≤ that of A0 + 5. Otherwise the result is
  "no improvement shown". Either outcome leaves defaults unchanged.
  `default_adoption` remains `false`.

### 7.5 Real-take pass (M12, conditional)

The input is the FULLER run `artifacts/runs/20261006T041633Z-990aa1bd6737`
`denoised.wav`, after manifest verification. It runs only after root confirms
the approved V6 private scratch location on honey. The pass reports beat and
downbeat counts and `half_double_ratio_vs_click_grid` against
`rhythm.analyze()` on the same input. There is no F-measure or accuracy. The
output is private and stays under the lane's ignored artifacts.

## 8. Root-owned changes requested (drafts; finalized in phase 2)

1. **`program/models.json`** gets one new key. Root fills `sha256` and
   `max_bytes` after its own explicit hash-bound fetch. Root does not commit the
   entry with the placeholder: `model_prefetch.py` rejects non-hex digests, and
   that refusal is intended.
   ```json
   "cpjku-beat-this-final0": {
     "url": "<exact final0 checkpoint URL from BEAT_THIS_QUALIFICATION.md>",
     "sha256": "TO_BE_FILLED_BY_ROOT_HASH_BOUND_FETCH",
     "max_bytes": "<published size rounded up, from research>",
     "format": "pytorch-lightning-ckpt (torch.load weights_only=True)",
     "license": "MIT (code and published weights, per upstream README; training-data rights distinct)",
     "source_commit": "<pinned CPJKU/beat_this commit>"
   }
   ```
2. **`program/tools.json` / `scripts/tool_api.py` / `scripts/mcp_server.py`**
   get descriptor drafts for `beat_this_compare` and `guitar_noul_decide`. Both
   are experimental, not default, and have closed schemas mirroring sections
   3.1/3.2 and 4.1/4.4. They are delivered as text in the lane handoff receipt.
3. **`just/workflow.just`** gets recipes `beat-this-runtime-setup`,
   `beat-this-runtime-check` and `beat-this-compare`, delivered as text.
4. **`program/linear.json`** has no change from the lane. Root records the
   facts.

## 9. Exact test protocol

Tests run from the worktree root, with no network and no FFmpeg (fixtures are
generated in-process). These are owned modules only, plus directly affected
modules:

```sh
PYTHONPATH=tests python3 -m unittest test_beat_this_compare -v
PYTHONPATH=tests python3 -m unittest test_guitar_noul_client -v
PYTHONPATH=tests python3 -m unittest test_benchmark test_rhythm -v   # directly affected readers, unchanged
```

**Fixtures in tests:**
- a temporary registry and model file (random bytes, its own sha256);
- a stub runner object returning fixed beats/downbeats (no torch import);
- `generate_fixture("c1-chug178", 3001)` truncated to 4 s, to check determinism
  (same seed gives an identical sha256) and the truth/prediction separation;
- a temporary run directory with a synthetic manifest
  (`source.kind:"generated_fixture"`) and a real-take-shaped manifest;
- a mock transport callable that records calls and returns canned responses,
  401, timeout, or malformed identity.

`socket.socket` and `urllib.request.urlopen` are patched to raise in every test
class.

Heavy numerics are limited to one job at a time with explicit timeouts. A1 runs
only on honey after root's fetch and runtime setup.

## 10. Receipts

The receipts are under `docs/agent-notes/sprints/20261007-s3/`:
- `model_lanes-contract-freeze.json` (this phase)
- `model_lanes-implementation.json`
- `model_lanes-experiment.json` (or a blocked receipt)
- `model_lanes-handoff.json`, which carries the root-owned drafts

Each cites R-N13 and records file hashes. Measurements, inferences and
unverified listening claims stay in distinct fields.

## 11. Phase 2 implementation notes (appended; sections 1–10 unchanged)

Phase 2 (2026-10-07) implemented sections 3–5 and 7 without changing any
preregistered fixture, seed, arm, scoring rule or decision rule. Deviations from
the phase-1 text, each with its reason:

1. **Runtime lock contents.**
   - `tqdm` is dropped. No inference-path module of `beat-this` 1.1.0 imports
     it (verified from source).
   - `soxr` is a compiled abi3 manylinux wheel, licensed LGPL-2.1-or-later. It
     is not pure Python. The lock carries the x86_64 and aarch64 wheels and
     selects by `platform.machine()`, because the honey architecture is
     unverified.
   - Versions are the upstream "known working" `einops` 0.8.0 and
     `rotary-embedding-torch` 0.6.4. `soxr` is 1.1.0, because 0.3.7 has no
     Python 3.14 wheel.
2. **Offline install.** Install is a verified self-extraction of the wheel
   members into the venv: no `uv` or `pip`, `--no-deps` semantics, and `.data`
   members are refused. `uv` availability on honey is unverified, and every
   locked wheel is pure or abi3.
3. **Unroutable proxy.** It is the closed loopback port
   `http://127.0.0.1:9`, which fails fast. Hub download is also disabled by
   replacing `beat_this.inference.load_checkpoint` and
   `torch.hub.load_state_dict_from_url` inside the worker.
4. **Unknown fields.** `UNKNOWN_FIELDS` holds the 13 exact values of 3.2 plus
   `intended_tempo_bpm: null` and `bar_lines: null`, making the 15 counted by M4.
5. **`insufficient_beats`.** This status means fewer than 4 beats, matching the
   minimum used by `rhythm.fit_click_grid`.
6. **Fixture background noise.** It uses uniform white noise
   (`random.random() - 0.5`) through the one-pole low-pass, rather than
   Gaussian noise, for speed. The output is still RMS-normalised to −42 dBFS.
   Determinism is per host and Python build (`math.sin`/`math.tanh` from the
   platform libm).
7. **Fixture inputs to the comparator.** These are
   `artifacts/s2/model_lanes/fixtures/<suite>/cases/<case>.wav`, bound by the
   suite `manifest.json`. `--generated-truth` is accepted only for `role: dev`
   suites. Held-out truth is read only by `score`, after `seal`.
8. **guitar_noul abstains.** A gateway's own abstain reason is kept as
   `gateway:<reason>`, so it stays distinct from client-side reasons. Non-200,
   non-401/403 statuses give `gateway_response_invalid` for every window.

Registry `max_bytes` for `final0` is the exact published content-length,
81,058,141 B. See `docs/research/BEAT_THIS_QUALIFICATION.md`.
