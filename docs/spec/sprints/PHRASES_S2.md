# S2 phrase lane: anchor-click arrangement spans, continuous-riff benchmark, V2 holdout receipt

Lane `phrase_anchor_riff`, sprint `20261006-s2`, Linear TIN-5603 (parent TIN-5599,
related TIN-5490). Branch `sprint/20261006-s2/phrase_anchor_riff`, worktree
`.local/sprint2/phrase_anchor_riff`, baseline `4b87484`. Authority: operator S2
resume prompt (`docs/agent-notes/2026-10-06-s2-resume.md`), `program/sprints/20261006-s2.json`,
repository `AGENTS.md`, R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13. Root signs
merges, owns Linear, catalog/MCP admission and publication. This file is the
phase-1 contract freeze; no numerics, generation or media decoding preceded it.

## 1. Scope

Three deliverables, each with its own claim boundary:

* **A. `scripts/phrase_anchor.py`** – deterministic arithmetic that expands the
  operator arrangement onto an existing fitted click grid from one anchor click,
  emitting source-timeline phrase/breakdown/rest spans with per-join confidence,
  explicit uncertainty and provenance, plus a scorer against operator-marked
  boundaries. Stdlib only; no audio decoding, no detector rerun.
* **B. `scripts/phrase_riff_s2.py`** – preregistered generated continuous-riff
  phrase-proposal benchmark (S1_FOLLOWUPS priority 1): frozen S1 baseline plus at
  most two arms, fresh held-out seeds, predictions globally sealed before truth.
* **C. V2 holdout-bank receipt** for the XORuby peer
  (`docs/agent-notes/peers/xoruby/V2-holdout-bank-receipt.json`) from the already
  admitted `benchmark_holdout.py` plan; audio stays gitignored.

Non-goals: no default detector/profile/master adoption; no typed MCP tool or
`program/tools.json` admission (research helpers only, as S1); no missed-note,
extra-note, rushed-breakdown or note-correctness verdict; no real-take phrase
accuracy claim; no model download, daemon, or host change; no change to S1
artifacts, accepted run `artifacts/runs/20261006T041633Z-990aa1bd6737`, or
`/Users/jess/Documents` / `/Users/jess/Desktop`.

## 2. Owned files

| Path | Role |
| --- | --- |
| `scripts/phrase_anchor.py` | A: anchor expansion + operator-boundary scorer (stdlib) |
| `scripts/phrase_riff_s2.py` | B: preregister / generate / discover / seal / score; C: `v2-bank` wrapper |
| `tests/test_phrase_anchor.py` | A tests (stdlib) |
| `tests/test_phrase_riff_s2.py` | B/C tests (stdlib; numpy cases skip with explicit reason) |
| `docs/spec/sprints/PHRASES_S2.md` | this contract |
| `docs/agent-notes/peers/xoruby/V2-holdout-bank-receipt.json` | C receipt |
| `docs/agent-notes/sprints/20261006-s2/phrase_anchor_riff-*.json` / `-*.md` | preregistration, dev-calibration, release, real-take spans, evaluation and results receipts |

Ignored outputs: `artifacts/s2/phrase_anchor_riff/` only. Root-owned files
(`scripts/tool_api.py`, `program/tools.json`, `just/workflow.just`,
`scripts/review_server.py`, `scripts/mcp_server.py`, `program/models.json`,
`program/linear.json`, `docs/spec/PROJECT.md`) are not edited; any needed
change is returned as `root_owned_changes_requested` text. Phase 1 requests none.

## 3. Frozen inputs (read-only, hash-bound at use)

| Input | SHA-256 at freeze |
| --- | --- |
| `program/demo-arrangement.json` | `170a33eb9e5832cbc0a3309c6041b5ded06f5fc1265ba519a6633ab0f84e541a` |
| `program/instrument.json` | `bd381207d6615814ebee694148357c00719739ec900aa69c96d71b20779707b0` |
| `scripts/arrangement_reference.py` (reference validation reused) | `c6bdc8991b6e378f2ab54873e94e23b1cff63073056e4f32b05ab5f7b58f89ae` |
| `scripts/phrase_proposal_s1.py` (S1 frozen worker, arms imported unchanged) | `38b736543a83d5c706a8803014f4e308685eee2c84275e9e6768c431b6b8d0e3` |
| S1 pins (`guitar_features.py`, `rhythm.py`, `phrase_evaluate.py`, guarded-arms note, instrument) | verified equal to `phrase_proposal_s1.PINS` at freeze |
| `scripts/benchmark_holdout.py` (V2 generator; last commit `f180572b8b51bd408debd55d661e670269d23b8f`) | `051d8689364564513c34a1ab00a2c23560407e474da12c2bf25e7513dbc81709` |
| Real-take click grid `artifacts/runs/20261006T034521Z-a0def0c43eac/clicks/20261006T040944Z-a98ce2dc1f72/clicks.json` | `cee9a506d70f3bebb95d054ae6a4bb5f8c880133d31327a8b7c0a19950497937` |
| Grid analyzed input (`denoised.wav` of that run) | `cb8a3fa559424810f206c94191a149156423770bbf91a13724a2ba28a44e879e` |
| Original source (`Movie on 10-5-26 at 3.38 PM.mov`, never opened by this lane) | `a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6` |
| Anchor candidates `docs/agent-notes/2026-10-06-operator-arrangement-click-anchor.json` | hashed at use; candidates came from the NR8 run (analyzed `26c9f42c…`), same original source and no-stretch timeline |
| Checker assessment `…a0def0c43eac/arrangement-reference-20261006/assessment.json` | optional cross-reference, hashed at use |
| Qualified FFmpeg `/nix/store/mv3x2v2p…-ffmpeg-headless-8.1.2-bin/bin/ffmpeg` | `3a315207e67de78e48c3bbb6b3346663f6a27c02e034d65ac72a12fee74c534a` (S1 pin) |

The real-take grid measured 88.80 BPM (period 0.675662 s, phase 0.510680 s,
coverage 0.991, median residual 5.32 ms, 219 observed events, beat indices 2–222,
`identity: periodic_high_frequency_transients_not_verified_metronome`). The
operator's approximate 178 BPM click is about twice that rate. That ratio is an
**operator-supplied mapping**, never inferred automatically (checker doctrine).

## 4. Deliverable A — `phrase_anchor.py`

### 4.1 Interface

```
python3 scripts/phrase_anchor.py spans \
  --clicks CLICKS_JSON --arrangement program/demo-arrangement.json \
  --clicks-per-grid-period {1|2} \
  (--anchor-lattice-index K | --anchor-seconds T) --anchor-source LABEL \
  [--anchor-evidence JSON] [--assessment CHECKER_ASSESSMENT_JSON] \
  --output NEW_FILE_UNDER_artifacts/s2/phrase_anchor_riff/
python3 scripts/phrase_anchor.py score --spans SPANS_JSON \
  (--boundaries BOUNDARIES_JSON | --annotation-store REVIEW_ANNOTATIONS_V2_JSON) \
  --output NEW_FILE_UNDER_artifacts/s2/phrase_anchor_riff/
```

Inputs are bounded, local, non-symlink regular files (JSON ≤ 16 MiB, duplicate
keys and non-finite numbers rejected). Outputs are new files only (exclusive
create, ≤ 2 MiB). Domain errors exit 2 with a bounded JSON reason. Inputs are
re-hashed after reading and must be unchanged.

### 4.2 Arithmetic (exact contract)

* Grid: `P = click_grid.period_seconds`, `phi = click_grid.phase_seconds_audio_relative`,
  `s0 = timeline.audio_stream_start_seconds`. `r = --clicks-per-grid-period`
  (required; only 1 or 2). Operator-click lattice period `p = P / r`; lattice
  time `t(k) = s0 + phi + k*p`, integer `k >= 0`. With `r = 2`, even `k`
  coincide with fitted grid beats (`beat_index = k/2`); odd `k` are
  **interpolated half-periods** and flagged, never called observed clicks.
* Anchor: `--anchor-lattice-index K` uses `k0 = K`. `--anchor-seconds T` snaps to
  `k0 = round((T - s0 - phi)/p)` and records the signed snap residual; refuse if
  `|residual| > p/4`. Anchor source label and optional evidence-file hash are
  recorded; anchor status is always `review_candidate_not_confirmed_downbeat`
  unless the evidence is an operator-authored mark.
* Expansion: the arrangement is validated with `arrangement_reference.validate_reference`
  and expanded in order to **27 units** (24 sixteen-click phrases, two eight-click
  breakdowns, one four-click rest) and **28 boundaries** `boundary:0..27`
  (IDs aligned with the checker), totalling **404 intended clicks**. Unit `i`
  spans arrangement clicks `[c_i, c_{i+1})`; boundary `b` lies at arrangement
  click `c_b` and source time `t(k0 + c_b)`. No count is ever forced to observed
  detections; nothing is moved to fit an observation.
* Source extent: units/boundaries whose time exceeds the grid PCM duration are
  kept with `coverage: "outside_source"` and null-free arithmetic times; they are
  not truncated or dropped.

### 4.3 Per-join confidence (heuristic, not probability)

For every boundary, measured components from the grid's `observed_events` in a
window of ±4 operator clicks around `t(k0+c_b)`:
`expected_grid_beats`, `observed_grid_beats`, `support_fraction`,
`median_abs_grid_offset_ms` (null if no events), `on_interpolated_half_period`.
Grid label: `grid_supported` (support ≥ 0.75 and median |offset| ≤ 30 ms),
`grid_weak` (support ≥ 0.25), else `grid_unsupported`. Structural status (all
that apply): `nominal`; `breakdown_execution_uncertain` (boundaries of
`breakdown1`, which the operator said may have been rushed or skipped, and of
`breakdown2`, intended only); `uncertain_upstream_breakdown` (every boundary
after `breakdown1` starts, i.e. `boundary:7..27` = 21/28, with the upstream unit
IDs listed); `presumed_repeat_section` (`chorus2` boundaries); `outside_source`.
`join_confidence` is the ordinal minimum of grid label and structural status
(`supported > weak > uncertain > unsupported`), with
`confidence_kind: "heuristic_not_probability"`. Thresholds are frozen here and
are engineering choices, not calibrated error bounds.

Uncertain breakdowns are **not forced**: each breakdown also emits
`downstream_shift_hypotheses` for −2, −1, +1, +2 clicks (all downstream boundary
times recomputed), labelled `hypothesis_not_adopted`. The primary expansion
always uses the intended eight clicks. Optional `--assessment` adds the
checker's per-boundary status (`matched_boundary_candidate` / unknown) as
cross-reference only.

### 4.4 Output fields that must be present

`schema_version`, `tool: "phrase_anchor"`, `status: "intent_projection_not_detection"`,
`units[]` (id, section_id, kind, click range, start/end source seconds, coverage),
`boundaries[]` (id, click index, lattice index, source seconds, grid components,
structural status, `join_confidence`, `confidence_kind`), `breakdown_hypotheses`,
`provenance` {`grid_sha256`, `grid_path`, `grid_analyzed_input_sha256`,
`original_source_sha256`, `arrangement_sha256`, `anchor` {source label, method,
input value, `k0`, snap residual, evidence sha256, evidence analyzed-input sha256},
`clicks_per_grid_period` with `mapping_basis: "operator_supplied_not_inferred"`,
`worker_sha256`}, and the explicit unknowns of §7. Real-take outputs carry
`real_take_phrase_correctness: "unknown_until_operator_marks_boundaries"`.

### 4.5 Operator-boundary scorer

Accepted marks: (a) lane JSON `phrase-boundaries-v1`
`{schema_version, source_sha256, marks:[{source_seconds, author:"operator", basis, note}]}`;
or (b) the annotation v2 store (`review-annotations-v2.json`, validated with
`annotation_v2.validate_store`), adapter rule: annotations with
`reported_by.actor == "operator"`, basis `operator_assertion` or
`operator_context`, status not `dismissed_candidate`, and kind `phrase_duration`
contribute their span start (and end when `extent_known`). Detector hypotheses
never count. This adapter convention is lane-local pending the annot_corpus
vocabulary (TIN-5604); a future `phrase_boundary` kind is added only by spec
amendment.

Source binding: marks must bind to the spans' `original_source_sha256` or to a
run derivative whose manifest proves the same no-stretch timeline; otherwise
`result: null, reason: "source_binding_mismatch"`. If fewer than **10** accepted
marks remain, `result: null, reason: "insufficient_operator_boundaries"`,
`accepted_mark_count`, `required: 10`. Otherwise one-to-one optimal matching
(`phrase_evaluate.optimal_matching`) between marks and the 28 primary boundaries
at **±100 ms** and at **±1 click** (`p` seconds), reporting hits / accepted
marks, signed offsets, MAE with denominator = hits (null when 0), per-boundary
structural status of matched joins, and marks outside the predicted extent.
Unmatched predicted boundaries are `not_reviewed`, never false positives (sparse
coverage); no precision is reported unless a fully reviewed interval is supplied.
Breakdown hypotheses may be scored only as labelled post-hoc diagnostics, never
selected.

## 5. Deliverable B — continuous-riff benchmark preregistration

### 5.1 Design (frozen now; exact numbers frozen in the machine preregistration)

Suite `s2-riff-1511-1613-v1`. Held-out seeds **1511, 1613** (fresh; consumed
seeds 211, 307, 617, 719, 1301, 1423 excluded). Development seed **1009** only
for §5.3. Eight cohorts × two seeds = **16 clips × 8 s = 128 s**, 48 kHz mono
PCM16, components `clean`, `fan`, `noise`, `click`, `mix` (S1 nuisance formulas
under the new namespace; clicks 0.337–0.393 s period independent of motif
tempo). All parameters derive from `sha256("s2-riff-1511-1613-v1:<seed>:<namespace>:<knob>")`
with motif, fill and nuisance namespaces kept separate. Guitar occupancy is
continuous across 0.5–7.5 s; tanh-distorted synthesis follows S1; pitches come
from the operator tuning MIDI 24–65 plus fret offsets 0–12; ~32.7 Hz content is
never filtered.

| Cohort | Construction | Reference pairs |
| --- | --- | --- |
| `b2b-picked` | fill X, motif A, gap g, A, fill Y; picked notes | 1 |
| `syncopated-palm-mute` | same layout; palm-muted chugs at off-beat/tuplet positions, fills at matching density | 1 |
| `legato-transition` | A, g, A legato glides then direct transition into a different legato phrase | 1 |
| `tapping-run` | A, g, A fast tapped run (soft 2–4 ms attacks, MIDI 51–77) between fills | 1 |
| `sweep-arpeggio` | A, g, A swept arpeggio (6–9 notes, 25–45 ms each, up/down) between fills | 1 |
| `aba-transition` | X, A, g, B, g, A, Y; B distinct; pair is (A₁, A₂) | 1 |
| `through-composed` (negative) | continuous playing, every segment a distinct note sequence | 0 |
| `sustain32-fan-click` (negative) | C1 ~32.7 Hz sustain + nuisance, no riff | 0 |

Gap `g ∈ [0, 0.10] s` for every positive; motif length `L ∈ [1.40, 1.90] s`
(ABA: `L ∈ [1.30, 1.70]`, `B ∈ [1.00, 1.40]`); start `a ∈ [0.9, 2.4]` s (ABA
`[0.7, 1.3]`). Truth spans are native-sample rounded before synthesis. Totals:
**12 positive reference pairs, 48 typed endpoints, 4 negative cases**.
Construction checks (structural failures, not quality metrics): component sum
within 2 PCM16 LSB of the mix; peak < 0.5; all gaps ≤ 0.10 s; **no silence cue**
— the longest sub-threshold run of the clean component (20 ms frames,
−40 dBFS) within ±0.25 s of every truth endpoint is not longer than the
longest such run inside the motif interior; fill/B sequences differ from A in at
least half their note positions. "Negative" means no generated recurrence
reference, not absence of music or repetition-free acoustics.

### 5.2 Arms (baseline + at most two)

* **Araw** – S1 frozen baseline, `phrase_proposal_s1.discover_source` unchanged.
* **S1_support** – S1 treatment, same call, settings unchanged (carried forward
  frozen; S2_multiscale output from that call is discarded before sealing and
  never scored, since S1 measured no difference).
* **R1_lag** – new contiguous arm: S1 log-band powers (`phrase_proposal_s1.extract`,
  bands ≤ 1800 Hz, same decoded 16 kHz PCM whose hash must equal the Araw/S1
  `analysis_pcm_sha256`), per-band z-score over the clip, frame cosine
  self-similarity; for lag `D ∈ [0.8, 4.5] s` and length `L ∈ [0.8, 2.4] s`,
  `L ≤ D`, the mean diagonal similarity over window `[t, t+L)` at lag `D` must
  reach threshold `θ`; maximal-length extension per `(t, D)`; proposals
  `([t, t+L), [t+D, t+D+L))`; S1 dedupe (both-span IoU 0.75), cap 10, spans
  0.5–4.0 s. No quiet-gap grouping. Lag-matrix recurrence follows the FMP
  self-similarity literature already cited in `docs/research/FOSS_AUDIO_MATRIX.md`.

### 5.3 Development calibration (before preregistration)

Only `θ` is chosen, from `{0.55, 0.65, 0.75}`, on dev seed 1009 (8 clips),
rule: maximize dev TP@IoU0.5 minus dev negative false candidates; ties → larger
`θ`. At most three dev runs, each ≤ 300 s. The dev receipt
`phrase_anchor_riff-dev-calibration.json` is committed before the preregistration
and its values are never reported as held-out results.

### 5.4 Preregistration, release, sealing

1. `phrase_riff_s2.py preregister OUTPUT` emits immutable metadata (suite,
   seeds, cohorts, full per-seed geometry, arms + settings including chosen `θ`,
   budgets, dependency pins, FFmpeg pin, scoring definition, claim flags). Its
   bytes are copied to `docs/agent-notes/sprints/20261006-s2/phrase_anchor_riff-preregistration.json`
   and **committed before any held-out generation**.
2. `generate`, `discover`, `score` each require `--plan/--plan-sha256` and
   `--release/--release-sha256`; they refuse (`preregistration_changed`,
   `preregistration_uncommitted`, `release_required`, `release_binding_changed`)
   unless the plan equals `metadata()`, the committed HEAD blob of the
   preregistration file has that SHA-256, the release's `prereg_commit` is an
   ancestor of HEAD, and the release binds plan, worker, pins, budgets and the
   phase. Releases are written only at the start of a root/workflow-authorized
   execution phase, quoting that authorization.
3. `discover` reduces the bank to opaque source paths + hashes and runs one
   bounded child per source (`_source`), which accepts no truth, cohort,
   reference, BPM or geometry. All 16 predictions are saved and globally sealed
   (`predictions-sealed.json`) before `score` opens any truth; `score` verifies
   every prediction hash and source binding first and re-verifies after.
4. No setting may be changed after held-out generation; a rerun would need new
   seeds and a new preregistration. Non-improvement is a valid result.

### 5.5 Scoring (frozen; `phrase_proposal_s1.score_rows` + `phrase_evaluate`)

Per arm: pair TP/FP/FN at both-span IoU **0.5 and 0.75** (maximum cardinality,
then maximum mean IoU) over **12** references; typed endpoint hits at
**20/50/100 ms** over **48**; endpoint MAE over matched pairs with explicit
denominator **4 × matched pairs** (null if none); common-reference MAE over
pairs matched by all three arms at IoU 0.5 (denominator 4 × common; null with
reason if empty); per-positive-cohort TP over 2; negative false candidates per
negative cohort over 2 cases each. Aggregates are sums, never averages of rates.
Abstentions stay in denominators. Result carries
`continuous_riff_accuracy_scope: "generated_only"`, `default_adoption: false`,
`settings_retuned: false`, `musical_performance_graded: false`.

### 5.6 Budgets

Held-out generation + discovery + scoring ≤ **900 s** wall under an external
`timeout`, ≤ 120 s per source child, 20 s FFmpeg decode (1 thread), 2 numeric
threads (`OMP/OPENBLAS/MKL/NUMBA_NUM_THREADS=2`), one heavy job at a time inside
the sprint heavy slot, JSON ≤ 2 MB, WAV ≤ 1 MB per file. Numerics use the locked
analysis interpreter `/Users/jess/git/video-utils/.venv/bin/python`
(numpy 2.5.3, librosa 0.11.0) via `VIDEO_UTILS_ANALYSIS_PYTHON`; no installs.

## 6. Deliverable C — V2 holdout-bank receipt

`phrase_riff_s2.py v2-bank --output artifacts/s2/phrase_anchor_riff/v2-bank-<UTC>`
imports `benchmark_holdout.py` (SHA must equal `051d8689…`), rebinds only its
output root (`ARTIFACTS`) to the lane directory, then runs the equivalent of
`holdout-plan` (canonical bytes must hash to the admitted
`495ad2f3f553b0bd7030ac797b6e8589f37748df657219c075d0fc4ce7491e74`),
`holdout-validate` and `holdout-generate` (internal timeout 600 s, external
660 s). The rebinding is recorded; generator bytes are unchanged. Bank: 12 cases
× 10 s = 120 s, 48 PCM16 components. The receipt records: plan SHA, recipe SHA,
generator SHA and commit `f180572b…`, per-case mix/component SHA-256, truth JSON
relative path and SHA, elapsed time, a byte-reproduction count against the
existing bank `artifacts/benchmarks/heldout-211-307-20261006T0020/fixtures.json`
(identical components / 48, truths / 12), licence line
`pending operator confirmation (repository MIT; proposed CC BY 4.0 for cross-repo use)`,
reserved seed range **2101–2199** (future evaluation-only V2 extensions; needs a
new admitted plan because the generator is fixed to 211/307), the statement
`training use of this bank voids video-utils held-out evaluation on it`, the
disclosure that seeds 211/307 were already used once by video-utils for the
frozen A/B/C/D phrase-window evaluation, `ground_truth_scope:
generator_only_not_musician`, and that transfer of audio to XORuby is a separate
root action (audio is never committed).

## 7. Unknown / abstain fields every output must carry

Anchor outputs: `real_take_phrase_correctness: "unknown_until_operator_marks_boundaries"`,
`observed_click_count: null`, `click_identity: "unverified"`,
`physical_capture_latency: "uncalibrated"`, `detector_delay: "uncalibrated"`,
`downbeat_confirmed: false`, `meter: "unknown"`, `breakdown1_execution: "unknown_operator_reported_possible_rush_or_skip"`,
`chorus2_count_provenance: "presumed_repeat"`, `performance_issue_confirmed: false`,
`missed_or_extra_notes: "not_assessed_no_approved_reference"`, `listening_acceptance: "not_performed"`.
Scorer: `result: null` plus `reason` whenever insufficient or unbound.
Benchmark: `continuous_riff_accuracy_scope: "generated_only"`,
`real_take_accuracy: "unknown"`, `confidence: null` per candidate,
`musical_phrase_identity: "unknown"`, `physical_articulation_accepted: false`,
`default_adoption: false`. V2: `quality_metrics: "not_evaluated"`,
`licence: pending operator confirmation …`, `listening_accepted: false`.

## 8. Test protocol

Run from the worktree root, stdlib interpreter:
`PYTHONPATH=tests python3 -m unittest test_phrase_anchor test_phrase_riff_s2 -v`.
Directly affected regression modules (unchanged sources, imported by this lane):
`PYTHONPATH=tests python3 -m unittest test_arrangement_reference test_phrase_proposal_s1 test_benchmark_holdout -v`.
Numpy-dependent construction checks run only under
`VIDEO_UTILS_ANALYSIS_PYTHON` and otherwise skip with a stated reason; skipped
tests never count toward the ≥ 10 minimum. Fixtures are synthetic in-test grids,
arrangements, mark files and temporary directories; no real media.

`tests/test_phrase_anchor.py` (≥ 8): (1) expansion 27/28/404 and click offsets;
(2) exact anchor arithmetic `t = s0 + phi + (k0+c)·P/r` on a synthetic grid;
(3) `--anchor-seconds` snapping, residual, refusal beyond `p/4` and missing/invalid
`r`; (4) half-period parity flagging; (5) uncertain joins: 21/28 upstream-breakdown
flags, breakdown and presumed-repeat statuses, no boundary moved; (6) grid support
labels from removed/offset synthetic events, `heuristic_not_probability`;
(7) outside-source retention; (8) provenance hashes and required unknown fields;
(9) scorer null below 10 marks, with detector-authored and dismissed marks excluded;
(10) scorer hits at ±100 ms and ±1 click, one-to-one, MAE denominator;
(11) source-binding mismatch null; (12) breakdown shift hypotheses not adopted.

`tests/test_phrase_riff_s2.py` (≥ 6): (13) deterministic preregistration metadata
and hash, seeds disjoint from consumed/dev seeds, geometry ranges, gaps ≤ 0.10 s;
(14) refusal when unreleased / uncommitted / plan changed / release mismatched;
(15) seal-before-score: refusal without a global seal, on a changed prediction,
and proof that no truth file is opened before all predictions verify;
(16) discovery child signature accepts no truth/reference argument;
(17) aggregate arithmetic: sums, MAE denominators, common-match null, per-cohort
negatives; (18) V2 wrapper refuses a changed generator or plan hash, confines
output, and emits the exact licence/training literals.

## 9. Completion metrics

| # | Metric | Denominator | Claim class |
| --- | --- | --- | --- |
| M1 | Arrangement expansion matches 27 units / 28 boundaries / 404 clicks | exact | arithmetic construction |
| M2 | Real-take spans emitted for each of the 3 cached anchor candidates (10.2775, 10.6275, 10.9775 s; lattice 29/30/31 under r = 2), none adopted | 3 outputs × 28 boundaries | inference (intent projection), not detection |
| M3 | Every boundary carries join_confidence + measured grid components; uncertain counts reported | 28 per output | heuristic measurement |
| M4 | `real_take_phrase_correctness` unknown on every real-take output; scorer returns null with reason until ≥ 10 operator marks exist | outputs; accepted marks | abstention |
| M5 | Preregistration committed (commit SHA) before held-out generation; dev receipt committed before it | git order | process evidence |
| M6 | Per arm: pair TP@0.5 and @0.75 | 12 references | measurement, generated only |
| M7 | Per arm: endpoint hits @20/50/100 ms | 48 endpoints | measurement, generated only |
| M8 | Per arm: endpoint MAE and common-reference MAE | 4 × matched pairs (stated) | measurement, generated only |
| M9 | Per arm: negative false candidates per negative cohort | 2 cases each | measurement, generated only |
| M10 | Held-out run elapsed ≤ 900 s; max per-source ≤ 120 s | 1 run; 16 sources | resource evidence |
| M11 | V2 receipt with all required fields; generation ≤ 600 s; reproduction identity | 12 cases / 48 components | construction evidence |
| M12 | Owned tests pass (≥ 10 executed, not skipped) plus 3 regression modules | test count | source check |
| M13 | No default/profile/master/catalog change; `default_adoption: false` | — | invariant |

Listening acceptance, real-take phrase accuracy and musical-mistake detection
are explicitly **not** completion states of this lane.

## 10. Phases

1. Contract freeze (this file; no numerics).
2. Implement A and B/C code + tests; dev calibration on seed 1009; commit dev
   receipt, then preregistration receipt.
3. On release: real-take anchor runs (stdlib, no decoding), V2 bank (≤ 600 s),
   held-out generate → discover → seal → score (≤ 900 s), one heavy job at a time.
4. Results receipt `phrase_anchor_riff-results.md` + evaluation JSON with exact
   hashes and denominators; hand off to root. Root posts V2 on TIN-5186.

## 11. Limitations

The grid is a constant-period global fit; local clock drift appears only as
measured event offsets near each join (the rhythm_clicks lane, TIN-5602, owns a
drift model; this lane consumes only the existing grid). The r = 2 mapping and
anchor are operator/review inputs; a one-click anchor error shifts every span by
~0.338 s, which ±1-click scoring tolerates but ±100 ms does not. Everything after
breakdown 1 inherits its unknown execution. Generated riffs are a synthetic recipe
family: they cannot establish real-take proposal accuracy, physical tapping/sweep
fidelity, or calibrated confidence; 12 positive pairs cannot estimate a population
rate. Activity/timbre gates and lag thresholds are uncalibrated heuristics.

## 12. Phase-2 implementation notes (additive; frozen sections 1–11 unchanged)

These record choices the freeze left open. None of them changes a frozen
value, seed, threshold, metric or claim boundary.

* **Anchor structural flags are derived generically** from the arrangement:
  every `kind: breakdown` unit flags its two touching boundaries
  `breakdown_execution_uncertain` and every later boundary
  `uncertain_upstream_breakdown`. Every `section_provenance: presumed_repeat` unit
  flags its touching boundaries `presumed_repeat_section`. On
  `program/demo-arrangement.json` this yields exactly the frozen sets: 6/7/15/16,
  7..27 (21/28) and 16..20. Boundaries after chorus 2 also list
  `upstream_presumed_repeat_units` (additive field).
* **Grid window:** the window contains the fitted beats `s0 + phi + j*P` within
  ±4 operator clicks that also fall inside the grid PCM extent. If one beat has
  several observed events, the smallest |offset| is kept. With no expected beats
  the label is `grid_unsupported` and `support_fraction` is null.
* **Operator-anchor evidence:** the status becomes
  `operator_marked_anchor_downbeat_unconfirmed` only when the evidence is a
  `phrase-boundaries-v1` file holding an `author: operator` mark within p/4 of
  the anchor. `downbeat_confirmed` stays false in every case. If evidence carries
  `source_sha256`, it must equal the grid's original source.
* **Scorer adapter:** `phrase-boundaries-v1` uses
  `schema_version: "phrase-boundaries-v1"`. The annotation store is checked with
  `annotation_v2.validate_store`, using the store's own source/manifest hashes and
  wide extent bounds (±86400 s). Source binding is then checked separately
  against the spans provenance. A run-derivative binding needs
  `timeline_no_stretch_verified: true` from the grid lineage. ±1 click means a
  tolerance of `p` seconds. Signed offset = predicted − mark.
* **Continuous-riff construction:** fill and B pitch sequences must differ from
  A in ≥ half of compared positions, both start-aligned and end-aligned. Every
  gap is occupied by one link note in the cohort's register (picked for ABA),
  so occupancy stays continuous. Palm-mute motifs contain a forced ≥4-step rest,
  and their fills draw inter-onset intervals ≤ 3 steps from A's own pool. This
  keeps the frozen no-silence-cue rule satisfied by construction, and it is
  still verified on the rendered clean PCM16. Pitches are integer MIDI 24–77,
  all reachable as an operator-tuning open string plus a 0–12 fret offset.
* **R1 ranking (frozen in the preregistration):** each `(t, lag)` keeps its
  maximal window with mean diagonal similarity ≥ θ. Candidates are ranked by
  excess `Σ(similarity − θ)` descending (ties: longer, earlier t, shorter lag),
  then S1-deduplicated (both-span IoU 0.75) and capped at 10. R1 has no
  activity/timbre gate, by design.
* **Release actor:** a release is either `actor: root` or
  `actor: root_workflow`. A `root_workflow` release is written by the lane at
  the start of a workflow-authorized execution phase and quotes that workflow
  task verbatim in `authorization_quote`. It binds plan, worker, pins, budgets
  and an ancestor `prereg_commit` whose preregistration blob has the plan hash.
* **V2 wrapper:** generation runs in a child process (`_v2_generate`) under the
  660 s external timeout. The admitted generator keeps its 600 s internal
  deadline. Only the module attribute `ARTIFACTS` is rebound.
