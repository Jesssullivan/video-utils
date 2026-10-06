# Queued follow-ups after S2

Status: queued on October 6, 2026. None of these items is active, and none
changes a default. S2 receipts stay as they are. Status per row is in
[PROJECT.md § S2 status](../PROJECT.md#s2-status--october-6-2026) and in the
[release record](../../agent-notes/sprints/20261006-s2/RELEASE.md). A row closes
only when its own completion evidence exists. A merged lane, a green test or a
Linear state does not close it.

## Priority 1: the operator and evidence gates that block musical claims

| # | Follow-up | Owner / decision | Completion evidence |
|---|---|---|---|
| 1 | **Operator labelling session and scoring.** Mark at least 10 phrase boundaries or issues on the real take in the local review UI, then score the frozen anchor candidates and automatic spans against them. | Operator marks; root runs the scorer | The v2 annotation store holds at least 10 accepted operator marks (detector-authored and dismissed marks excluded). A `phrase_anchor` score receipt records hits at ±100 ms and ±1 click, the MAE denominator equal to hits, and unmatched boundaries as `not_reviewed`. Until this exists, `real_take_phrase_correctness` stays `unknown_until_operator_marks_boundaries` ([PHRASES_S2](PHRASES_S2.md), [results](../../agent-notes/sprints/20261006-s2/phrase_anchor_riff-results.md)). |
| 2 | **Push and hosted CI on the final head.** `4be2812`, `ebaf72d`, `3e397ad`, `46aee65` and `e3ef39b` are merged locally, but at release time the remote `main` was at `4ec475e`. | Root | A signed push, then a `root-hosted-ci-<run>.json` with conclusion success on the pushed head, recording Python, Rust and secret-scan results. |
| 3 | **Capture-latency calibration and phrase-timing direction.** Real-take direction is `withheld_uncalibrated`, and `direction_policy.operator_calibration` is null. | Operator measures latency; root decides the schema | An operator-measured capture-latency procedure and receipt. A schema/descriptor change that adds a calibration input, with tests. Real-take direction is published only when calibrated ([root_admission_d](../../agent-notes/sprints/20261006-s2/root_admission_d-receipt.json)). |
| 4 | **Tone A/B listening preference.** `operator_preference` is null. The low-end fullness and thin/nasal feedback is not closed. | Operator | A recorded blind preference with uncertainty on the three level-matched excerpt pairs. Note the measured excerpt-pair loudness difference of up to 1.00 LU. The listening-review fields must stay separate from measurements ([tone A/B run](../../agent-notes/sprints/20261006-s2/tone_ab-20261006T120702Z-actual-run.md)). |
| 5 | **EQ floor below 160 Hz decision.** The FULLER EQ schema minimum is 160 Hz. The 100 Hz low-shelf trial (+1.31 dB matched at 20–45 Hz) is `rejected_or_unreviewed_trial`. | Root plus operator | A written decision, plus either an unchanged schema or a new reviewed profile version with a matched A/B, 32 Hz protection checks and an attack-preservation check. The decision must not claim that EQ recovers an uncaptured fundamental. |

## Priority 2: decisions and text that S2 left pinned

| # | Follow-up | Owner / decision | Completion evidence |
|---|---|---|---|
| 6 | **Quarto flake fix.** At the locked nixpkgs rev, `quarto-1.10.18` defaults to `pandoc-cli-3.7.0.2`, which rejects the `syntax-highlighting` option. | Root changes `flake.nix`/`flake.lock`; operator approves the render attempt | A flake change (options A/B/C in [report_d6 handoff](../../agent-notes/sprints/20261006-s2/report_d6-handoff.json)), then one approved, bounded render attempt with a receipt giving the HTML sha256, the Quarto/R/pandoc versions and a remote-reference scan. A successful render does not mean report readability or listening acceptance. |
| 7 | **`phrase_timing` frozen descriptor wording.** `tools[37].intent` still says "whether each phrase tends ahead of or behind the recorded click". | Root decision: rebase the `tools[:38]` freeze or leave the text | A descriptor change with a new freeze hash, updated pins and a skill/descriptor consistency test, or a recorded decision to keep it. |
| 8 | **`report_bundle` skill wording.** The skill still says "MCP tool `report_bundle` (once admitted by root)", although the tool is now admitted as tool 40. | Root or lane text decision | Skill text promoted, `report_bundle_skill_sha256` pin updated, and the MCP prompt readback test passing. |
| 9 | **V6 privacy wording and the V2 licence line.** The root draft is held. The V2 bank licence is pending (repository MIT; CC BY 4.0 proposed for cross-repo use). | Operator approval | Approved wording committed beside the [V2 receipt](../../agent-notes/peers/xoruby/V2-holdout-bank-receipt.json), then posted on TIN-5186. Real-take-derived outputs stay private until then. |
| 10 | **MCP `denoise` and FULLER (RQ-M1b).** The MCP `denoise` default is still `conservative3` because `tools[:32]` is frozen. | Root decision | Either a separate typed tool for FULLER with a reviewed capture interval, or a recorded freeze rebase with tests. The text in `profiles/fuller.json` that still says binding "fails closed until supported" changes only with the corresponding pin updates. |

## Priority 3: capability proof that needs a host, data or a new take

| # | Follow-up | Owner / decision | Completion evidence |
|---|---|---|---|
| 11 | **Second take ingestion** (the operator said a second take would exist by 2026-10-09). | Operator supplies; root runs | A fresh source hash, its own reviewed capture interval, and a full `demo` run with its own run directory. Corpus split by take family. No settings tuned on the held-out family. Until it exists, V1 stays at n=1. |
| 12 | **Beat This comparator.** It is still not run. | Root, with capacity on honey (CPU), not sting | An exact registry entry (artifact, licence, hash), then a bounded run on the fixtures and the take with tempo-ambiguity alternatives kept, as a comparator only. The default stays usable without weights. |
| 13 | **Native editor import proof.** FCPXML 1.10 and Resolve export exist. `application_import` is `not_performed`, `host_frame_id` is null and the DTD is unvalidated. | Operator-provided application host | An import receipt from the actual application: version, displayed marker positions compared with source time, and drop-frame/non-drop-frame handling. The real take stays `calibration_required` until PTS-aware alignment is shown. |
| 14 | **AU registration and Logic.** Stage 2 discovery is `blocked_not_installed`. Stages 3–5 and the Logic host check were not performed. | Operator-approved stage-1 install ([AU_HOST_ACCEPTANCE_LANE](../AU_HOST_ACCEPTANCE_LANE.md)) | Separate receipts for registration, the registered render, parameters/state, auval and Logic playback. Each states the realtime deadline and the instantiation mode it observed. |
| 15 | **Memory ceiling.** `memory_ceiling_bytes` is null and no RSS limit is enforced. | Root | A measured peak RSS per stage on the fixtures and the take, a declared limit, and a test that refuses when the limit is exceeded. |
| 16 | **Hosted web access.** This stays LATER (TIN-5552). | Separately estimated milestone | Private-host qualification per [MILESTONES § C](../future/MILESTONES.md): host/access/retention/resources and measured SLOs. Local WEB proof is not hosted proof. |

## Housekeeping before any worktree is reclaimed

- Copy gitignored lane artifacts into the main checkout's `artifacts/s2/` first.
  `phrase_anchor_riff`, `robustness`, `tone_ab`, `ui_core` and `web_ui_binding`
  are already copied. `au_auval`, `fuller_profile`, `report_d6`, `rhythm_clicks`,
  `share_export_fix`, `web_jobs` and `web_reliability` were not yet copied at
  release time. The tone A/B listening excerpts also need to be in a durable
  location (root_admission_d deferral).
- Bring `program/sprints/20261006-s2.json` up to date with the merged state.
  It still shows robustness/report_d6 as `running`, web_reliability as
  `queued_wave2` and `tool_count` 39. `program/linear.json` also needs to be
  synchronized with the S2 issue states. Both are root-owned.
- Fix the `tone_ab` finalize reserve gap and run `report_bundle` successfully
  end to end through MCP. Both are lane code changes deferred by root.
- Stems stay deferred until the pretrained weights have qualified licence terms
  ([FOSS audio matrix](../../research/FOSS_AUDIO_MATRIX.md), row 11).
