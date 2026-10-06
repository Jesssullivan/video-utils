# S2 ui_core: practice UI stage identities, matched A/B, coverage strip, triaged flags

Lane `ui_core`, sprint 20261006-s2, Linear TIN-5610. Branch
`sprint/20261006-s2/ui_core`, worktree `.local/sprint2/ui_core`, baseline
`0cdca01`. Authority: S2 sprint task, repository `AGENTS.md`,
R-HOOK-CONVERGENCE-20261004 (TIN-3692 comment
98cf680c-7299-4949-bfb2-60079053ad43; R-N11/R-N12/R-N13). This file is the
**Phase 1 contract freeze**. No numerics, media decoding, browser or server ran
before this commit. Read-only inspection covered existing JSON receipts and the
read-only `review_server.Session(..., open_media=False)` constructor on both
real runs. Root alone signs merges, edits root-owned files, writes Linear and
publishes.

Reused, not redecided: [REVIEW_UI_S1](REVIEW_UI_S1.md) (source-clock transport,
v2 issue form, replay and stale semantics), [ANNOTATIONS_S1](ANNOTATIONS_S1.md)
and `scripts/annotation_v2.py` (store, bases, `claim_label`),
[TONE_S2](TONE_S2.md) and the `tone-ab.json` schema,
[ANNOT_CORPUS_S2](ANNOT_CORPUS_S2.md) and the `flags-triage.json` schema,
[PHRASES_S2](PHRASES_S2.md) with `scripts/phrase_anchor.py` (spans and the
`score` mark rule), [RHYTHM_S2](RHYTHM_S2.md) with `scripts/phrase_timing.py`,
and [OVERLAYS_AND_ANNOTATIONS](../future/OVERLAYS_AND_ANNOTATIONS.md) (Compact
default, INTENT / REVIEW / USER REPORTED labels, text plus shape and colour).

## 1. Question and scope

The operator needs one local practice page for the real take. It shows which
signal versions each panel used. It lets the operator hear source against the
accepted FULLER delivery at matched level. It shows where the arrangement intent
and the detectors place phrases, and the triaged review flags. It also supports
a fast labelling session whose marks the phrase-anchor scorer can consume. The
page orders and displays evidence. It never grades the performance, never
records a listening verdict on the operator's behalf, and never adopts a
detector, profile, anchor or master.

In scope:

1. A **stage identity strip**: source, tone and arrangement stages, plus the
   analysis input each layer consumed. Each shows a 12-hex short hash with the
   full hash in the accessible name and inspector.
2. A **matched A/B pair**: the tone_ab blind excerpt pairs (source against
   FULLER `delivery_master`). It shows the measured region `match_lu_delta`,
   per-file informational LUFS and the static gain. The label reads
   `operator_preference: not recorded`. An optional third player carries the
   **lowshelf trial**, labelled as an unadopted, unreviewed experiment.
3. An **intended-vs-observed coverage strip** on the source timeline. One lane
   holds the INTENT arrangement units from `phrase_anchor` spans. Another holds
   the DETECTOR HYPOTHESIS spans from `phrases.json`
   `observations.proposed_review_spans`. A third holds USER REPORTED marks.
   Join boundaries are styled by `join_confidence`, and uncertain or weak joins
   carry text and shape markers, not colour alone.
4. A **triaged flags default view** from `flags-triage.json`. It shows at most
   one item per triage window, exactly as the triage file's `shown` list holds
   them. Navigation proxies sit behind a toggle that defaults off, and
   suppressed items sit behind a second toggle. The window basis is shown
   verbatim. On the real take it is click-grid navigation windows, not phrases.
5. **Per-phrase timing offsets** from `phrase-timing.json`. These are
   measurements labelled `unvalidated`. They show the signed median in ms, the
   IQR, the click-proximal count and the abstain reasons. They never use the
   words rushed, dragged or late, or any other verdict wording.
6. **Prototype labels** on parts that are not implemented (section 6).
7. A **labelling session mode** for marking at least 10 phrase boundaries or
   issues quickly. Marks are saved through `/api/annotations-v2` with the
   existing replay and conflict semantics.
8. **No autoplay** anywhere, and **keyboard navigation** for every new control.
9. A **walkthrough** at 375 px, 390 px, desktop 1440 px and 200 % zoom in an
   owned headless Chrome, recorded as a receipt or skipped with a reason.

Out of scope (not claimed): any edit to root-owned files (requested only, see
section 9); preference capture or storage; listening acceptance; rendering
overlays into video; editor import; staff or tab; new DSP, EQ or loudness
processing of whole takes; re-running detectors, `phrase_anchor`,
`phrase_timing` or `tone_ab`; Linear writes; model downloads; daemons; and any
write to `artifacts/runs/*`, `/Users/jess/Documents` or `/Users/jess/Desktop`.

## 2. Owned files

| File | Role |
| --- | --- |
| `review/index.html` | Adds the S2 sections; every S1 element id and order of S1 sections is preserved |
| `review/style.css` | S2 styles; 390 px layout; badge shapes; no horizontal overflow |
| `review/practice_s2.js` | New classic script: S2 panels, quick-mark queue, keys. No `innerHTML`, no `.play()`, no `autoplay` |
| `review/practice_s2_bundle.py` | Read-only composer. It verifies inputs and writes one bundle directory (section 4) |
| `review/practice_s2_routes.py` | Route helpers that root wires into `review_server.py` (section 9); stdlib only |
| `review/make_practice_fixture_s2.py` | Fresh synthetic run plus synthetic S2 layers under `artifacts/` (never a real take) |
| `review/browser_smoke_s2.py`, `review/browser_smoke_s2.mjs` | Owned-Chrome CDP walkthrough (section 8.3) |
| `tests/test_review_ui_s2.py` | ≥ 10 tests (section 8.1) |
| `docs/spec/sprints/REVIEW_UI_S2.md` | This contract |
| `docs/agent-notes/sprints/20261006-s2/ui_core-*.json` | Contract freeze, test, walkthrough and handoff receipts |

`review/app.js`, `review/practice.js`, `review/browser_smoke.*` and
`review/make_practice_fixture_s1.py` stay byte-identical unless a defect forces
a change. Any such change is listed in the handoff with its reason. The S1
module `tests/test_review_ui_s1.py` is not lane-owned and must keep passing
13/13 unchanged. As a consequence, the S1 issue panel keeps its frozen
`DETECTOR HYPOTHESIS` / `REFERENCE COMPARISON` label strings. S2 panels use the
annotation_v2 `claim_label` instead (section 5.4). The handoff records this
known divergence for root.

Generated outputs go only under
`.local/sprint2/ui_core/artifacts/s2/ui_core/` (gitignored `/artifacts/`).

## 3. Real-take inputs (read-only)

| Role | Path | Binding |
| --- | --- | --- |
| Session run (tone stage, accepted FULLER) | `artifacts/runs/20261006T041633Z-990aa1bd6737/` | original source `a522115f4e72…`, manifest `61c9b3930c36…`; `denoised.wav` `26c9f42c2bb2…`, `processed.wav` `bd41286de40e…`, `cleaned.wav` `9ed50aeca134…` |
| tone_ab output | `.local/sprint2/tone_ab/artifacts/s2/tone_ab/20261006T041633Z-990aa1bd6737-20261006T120702Z/` | `tone-ab.json` `run.source_sha256` must equal the session's original source; each excerpt and trial file sha256 must equal its tone-ab.json record |
| Analysis run (flags, detector phrases) | `artifacts/runs/20261006T034521Z-a0def0c43eac/` | same original source; analyzed input `cb8a3fa55942…` (**differs** from the tone stage `denoised.wav`) |
| flags-triage | regenerated in Phase 2 by `python3 scripts/flags_triage.py <analysis run> --output artifacts/s2/ui_core/real-take/flags-triage.json` (read-only on the run). The expected denominators are total 171, shown 15, navigation hidden 112, suppressed 44 (annot_corpus receipt, output `b4c5961fc02e…`) | `source_sha256` equals the original source; `flags_sha256` recorded |
| Arrangement intent spans | `.local/sprint2/phrase_anchor_riff/artifacts/s2/phrase_anchor_riff/real-take/spans-k29.json`, `-k30`, `-k31` (none adopted) | `provenance.original_source_sha256` equals the session's; `arrangement_sha256` `170a33eb9e58…` equals `program/demo-arrangement.json` |
| Phrase timing | `.local/sprint2/rhythm_clicks/artifacts/s2/rhythm_clicks/phrase-timing/20261006T122429Z-173f5f0a0e04/phrase-timing.json` (arrangement-marker basis) and `…20261006T122430Z-72058cbed827/…` (automatic span basis) | `inputs.analyzed_input_sha256` `cb8a3fa55942…`; `real_take_status` `unvalidated_until_operator_spot_check` |

Inputs that live in other lanes' ignored worktree directories are copied into
the bundle with verified hashes, so the page never depends on another
worktree's lifetime. When a sibling path is missing at Phase 2, that layer is
`unavailable` with reason `input_missing` and nothing is fabricated.

## 4. Bundle composer (`review/practice_s2_bundle.py`)

CLI:

```
python3 review/practice_s2_bundle.py compose --session-run RUN --output DIR \
  [--tone-ab DIR] [--flags-triage FILE] [--detector-phrases FILE] \
  [--phrase-spans FILE ...] [--phrase-timing FILE ...] \
  [--arrangement program/demo-arrangement.json] [--trial-excerpts] [--timeout-seconds T]
```

Every layer argument is optional. A missing or refused layer becomes
`layers.<name> = {"status": "unavailable", "reason": <code>}`, and the page
still renders.

Refusals (no output directory is published):

- `output_exists`, `output_inside_runs` (the output resolves inside any
  `artifacts/runs/*`), and `output_outside_artifacts` (it must be under this
  worktree's `artifacts/`).
- `session_manifest_unreadable`, `session_source_hash_required`.

Per-layer refusals (the layer becomes unavailable and the rest continue):
`layer_source_mismatch`, `layer_hash_mismatch`, `layer_schema_unknown`,
`layer_input_too_large` (> 20 MB JSON) and `media_extent_mismatch` (an excerpt
must have `frames_per_file` frames at the recorded rate and channels, read from
the RIFF header with stdlib only).

Work happens in a staging directory that is renamed into place. All inputs are
opened read-only and hashed before and after, and a change during compose
refuses the layer with `input_changed_during_compose`.
`--trial-excerpts` is the only media job. It runs one FFmpeg process at a time
(env `FFMPEG`), `atrim=start_sample=a:end_sample=b`, then
`volume=<trial gain_db>dB:precision=double`, written as f32 WAV. It uses the
**exact** excerpt sample windows and the `loudness_match.per_arm.trial_lowshelf.gain_db`
from tone-ab.json. Each subprocess timeout is min(120 s, remaining), the total
default is 600 s, and the maximum is 1800 s. The frame count is verified after
writing. The trial excerpts are **unblinded** and always labelled TRIAL.
Without FFmpeg, the trial is `unavailable` / `ffmpeg_not_resolved`.

`bundle.json` (`schema_id: "video-utils.practice-s2.bundle"`, `schema_version: 1`)
contains:

- `session_binding`: `run_id`, `manifest_sha256`, `original_source_sha256`,
  `source_extent_seconds`.
- `stages`:
  - `source`: the original sha256 and `source.wav` sha256.
  - `tone`: run id, profile name from `applied-profile.json`, and the
    denoised, processed and cleaned sha256 values.
  - `arrangement`: the arrangement sha256, each spans file sha256 and its
    anchor `k0`/status, and `adopted: false`.
  - `analysis`: for each layer, its `analyzed_input_sha256`,
    `matches_tone_denoised` (bool) and `timeline_no_stretch_verified` (copied,
    or `null` when absent).
- `layers.tone_ab`: copied verbatim. This covers `loudness_match`,
  `excerpts.pairs` (files, sha256, static gain, informational LUFS, sample
  peak), `excerpts.blind_key`, `operator_preference`, `experiment` (status,
  controls, adopted), `limitations` and `unknown_field_reasons`.
- `layers.coverage`: `intent` (units and boundaries per spans file, with
  `join_confidence`, `structural_status`, `on_interpolated_half_period`,
  `checker_status`), `detector` (`proposed_review_spans` with kind, label,
  confidence and uncertainty, verbatim), and the input sha256 values.
- `layers.flags_triage`: the triage document verbatim (`shown`, `suppressed`,
  `hidden_navigation`, `denominators`, `window_basis`, `priority_rule`) plus
  its sha256.
- `layers.phrase_timing`: one entry per file, verbatim plus its sha256.
- `media`: name → `{file, sha256, frames, sample_rate, channels, role}`.
- `claim_boundary` (fixed): `listening_acceptance: "not_established"`,
  `musical_verdict: "not_established"`,
  `missed_or_extra_notes: "not_assessed_no_approved_reference"`,
  `default_adopted: false`, `master_changed: false`,
  `operator_preference: "not_recorded"`.
- `unknown_fields` (section 7) and `composer_sha256`.

## 5. Page behaviour (`review/practice_s2.js`)

The script loads after `practice.js` and listens for `review-ready`. It fetches
`/api/practice-s2` once. It refuses the bundle in the UI when
`session_binding.original_source_sha256 ≠ session.source_sha256` or
`manifest_sha256 ≠ session.manifest_sha256`, with the message "S2 evidence
belongs to another recording". If the route is absent (404) or refused, every
S2 panel shows an unavailable reason and every S1 control keeps working. All
text is rendered through `textContent`.

### 5.1 Stage identity strip

The strip has one row per stage: Source, Tone (FULLER), Arrangement intent, and
one Analysis input row per distinct analyzed input. Each row shows the label,
the 12-hex short hash, its role and status. The full hash appears in a
`<details>` inspector. When an analysis input differs from the tone denoised
hash, the row shows `analysis input differs from tone stage — bound by original
source only`, plus the no-stretch flag value or `unknown`.

### 5.2 Matched A/B pair

There is one pair at a time, with a pair selector for 1–3. Each pair has two
`<audio controls preload="none">` players labelled **X** and **Y**. The mapping
stays hidden until the operator presses **Reveal which is FULLER**. This is a
local display toggle. It is never saved, and it is not a preference. The
following are always shown:

- `region match: ±<match_lu_delta> LU over <start>–<end> s (measured, BS.1770 via FFmpeg loudnorm)`;
- per-file `static gain <g> dB`, `excerpt LUFS <v> (informational)` and `sample peak <p> dBFS`;
- `operator_preference: not recorded` and `listening acceptance: not established`.

When the trial is available, a third player is labelled
`TRIAL · lowshelf 100 Hz +1.5 dB · unreviewed experiment · not adopted`.
Starting one player pauses the others, which uses only `pause()`. No code calls
`play()`, sets `autoplay` or plays on key or selection.

### 5.3 Coverage strip

The strip spans source seconds 0 to `source_max_seconds`. It has three lanes,
INTENT, DETECTOR HYPOTHESIS and USER REPORTED, each with a text lane label. An
anchor selector chooses k29, k30 or k31 and shows `anchor review candidate · not
adopted · ±1 click alternatives`. Boundary ticks are styled as follows:

- `supported`: solid tick;
- `weak`: dashed tick with a "~" text glyph;
- `uncertain`: hatched band plus a "?" text glyph, `aria-label` "uncertain join";
- `structural_status` containing `breakdown_execution_uncertain` or
  `uncertain_upstream_breakdown`: range bracket text `≈`.

Units with `coverage` other than `within_source` show an `outside source` text
label. The summary line uses denominators only:

- `intent units within source: a/b`;
- `boundaries by join confidence: supported s, weak w, uncertain u (of n)`;
- `detector review spans: m`.

Overlap between the lanes is not called agreement, accuracy or correctness.
Clicking a unit seeks the source clock without playing.

### 5.4 Basis badges

Each badge uses text, shape and colour.

| Record | Badge text | Shape |
| --- | --- | --- |
| v2 `operator_assertion` | `USER REPORTED` | solid pill |
| v2 `operator_context`, phrase_anchor arrangement units | `INTENT` (arrangement units add `· projected`) | bracket outline |
| v2 `detector_hypothesis` | `REVIEW` (store `claim_label`) + subtitle `detector hypothesis` | dashed pill |
| v2 `reference_comparison` | `REFERENCE REVIEW` (store `claim_label`) | double outline |
| triage `shown` flags, phrases.json spans, raw markers (not in the v2 store) | `DETECTOR HYPOTHESIS` | dotted pill |
| anything else | `UNKNOWN BASIS` | plain |

For v2 records the S2 page prefers the store's `claim_label` and falls back to
the `annotation_v2.LABELS` mapping above.

### 5.5 Triaged flags

The default list is `flags_triage.shown`, in triage order. Each row shows the
window id, `window_basis.kind` (on the real take: `click-grid navigation window
— not bar, phrase or meter`), the flag kind, the source span, the tier and the
DETECTOR HYPOTHESIS badge. The header shows `shown S of T flags · navigation
hidden H · suppressed P` from `denominators`. The toggles **Show navigation
proxies (H)** and **Show suppressed (P)** default to unchecked and render the
retained records verbatim. Numeric confidence is never displayed as a
probability or used for ordering. When the window basis is `phrase_spans`, the
view reads "at most one per phrase span". Otherwise it reads "at most one per
navigation window".

### 5.6 Phrase timing

There is one table per timing file. Its header reads `MEASUREMENT · unvalidated
until operator spot check · click identity unverified · capture latency
uncalibrated`. Each row shows the phrase label and its `label_basis`, the span,
the status, `median offset <±x.x> ms` (delay-compensated when available, with
the basis named), the IQR, `click-proximal n`, the direction column and the
abstain reason. Each file line names its `run_kind` and the direction policy.

The composer reads phrase_timing **schema 2** (main `84ee740`, root_admission_d,
audit finding 9). Direction is shown only when the file's `run_kind` is
`synthetic_fixture` and the row's `direction_status` is
`synthetic_known_offset_fixture`; the class then reads `within ±5 ms of
modelled click`, `ahead of modelled click` or `behind modelled click`, followed
by `· synthetic known-offset fixture`. Every other measured row, including
every real-take row (`direction: null`, `direction_status:
withheld_uncalibrated`), reads `direction withheld (uncalibrated)`. The signed
median and IQR remain visible as measurements. The composer refuses schema 1
(`layer_schema_superseded`, since it carried real-take `tendency_label`s) and
any schema-2 file whose direction fields break that policy
(`layer_direction_policy_violation`): a real take with a non-null direction or
a synthetic status, a synthetic measured row without a direction class, or an
abstained row with direction fields. A row with `tendency_label` is
`layer_schema_unknown`. The UI never shows the words "rushed", "dragged", "late", "early", "mistake", "error",
"wrong", "missed", "sloppy" or "tight" in generated text. An abstained row shows
`—` and its reason, never 0.

### 5.7 Labelling session mode

The **Labelling session** toggle adds a quick-mark bar beside the source
transport. It has a template-text input that the operator owns and edits, for
example "phrase boundary", a kind selector (default `phrase_duration`, plus the
other v2 kinds), a certainty selector (default `uncertain`), a queue list, and
**Save queued marks**. The keys work only when the focus is inside the transport
or the quick-mark bar. They never fire while the operator types in a field or
holds a modifier.

- `B` queues a **point** mark at the current source time: `kind
  phrase_duration`, `basis operator_assertion`, `reported_by
  {operator, browser}`, `extent_known false`. The `operator_quote` is the
  template text exactly as typed. The `note` is `quick mark (key B) at
  <clock>; template text`.
- `I` queues a point mark of the selected kind.
- `N` and `P` seek to the next or previous intent boundary. `Shift+N` and
  `Shift+P` seek to the next or previous shown triaged flag. They never play.
- `U` removes the last queued, unsaved mark.
- S1 keys (`←` `→` `[` `]` `L`) are unchanged.

Saving sends one POST per mark, in order, each built like S1
`buildIssueRequest`. Each carries its own `browser-<uuid>` idempotency key and
the latest `revision`. The semantics are:

- A success removes the mark from the queue.
- A transport error, a 5xx or a malformed success freezes the queue head with
  its exact bytes and key, and shows **Retry same mark**. A replay reconciles
  without a duplicate.
- `stale_annotation_revision` refreshes the store, keeps the remaining queue
  with fresh keys, and requires a new explicit save.
- Any other 4xx keeps that mark in the queue with its error code and stops.
- The queue is disabled while the S1 issue form holds a busy or uncertain save,
  and vice versa.

Marks never carry `candidate_id` unless that id is in `session.markers`. On the
FULLER session there are no markers, so a flag reference goes into the `note`
text instead. The queue lives in page memory only. Leaving the page shows the
standard unsaved-changes prompt while the queue is non-empty.

Every saved `phrase_duration` mark with an operator basis is acceptable to
`phrase_anchor.marks_from_annotation_store` (actor operator, basis
operator_assertion, status ≠ dismissed). Section 8.1 test 12 verifies this end
to end on a synthetic store.

## 6. Prototype labels

Each of the following carries a visible `PROTOTYPE · not implemented` badge and
has no active controls:

- Compact overlay preview (section label, BPM, issue badges) — not rendered.
- Operator preference capture — not stored.
- Editor marker export from this page.
- Staff or tab view.
- Click-drift timeline.

## 7. Unknown fields the bundle and page must carry

These keys must be present with the stated value, plus a reason string:

- `operator_preference` (null, "not recorded");
- `listening_acceptance` (`not_established`);
- `perceived_fullness`, `nasal_quality` and `fundamental_32hz_presence` (null,
  copied from tone-ab `unknown_field_reasons`);
- `monitoring_device` (null);
- `true_peak_dbtp` (null where tone_ab left it null);
- `fan_only_gain` and `music_only_gain` (null);
- `click_identity` (`unverified`);
- `physical_capture_latency` (`uncalibrated`);
- `detector_delay` (`uncalibrated`, or the phrase_timing value when it is
  given);
- `meter` (`unknown`);
- `downbeat_confirmed` (false);
- `anchor_adopted` (false);
- `breakdown1_execution` (`unknown_operator_reported_possible_rush_or_skip`, copied
  verbatim as operator context);
- `real_take_phrase_correctness` (`unknown_until_operator_marks_boundaries`);
- `missed_or_extra_notes` (`not_assessed_no_approved_reference`);
- `phrase_timing.real_take_status` (`unvalidated_until_operator_spot_check`);
- `browser_level_match` (`excerpt files pre-gained by tone_ab; browser output
  level and device unmeasured`);
- `walkthrough_listening` (`not_performed`; browser playback is muted).

## 8. Test protocol and completion metrics

### 8.1 Unit and behaviour tests: `tests/test_review_ui_s2.py`

Run from the worktree root:

```bash
PYTHONPATH=tests python3 -m unittest test_review_ui_s2 -v
PYTHONPATH=tests python3 -m unittest test_review_ui_s1 test_annotation_v2 -v   # directly affected modules
```

JavaScript tests run the shipped `review/practice_s2.js` under Node (`vm`) with
the S1-style element, fetch and players doubles (`skipUnless` node). Python
tests use fixtures from `review/make_practice_fixture_s2.py` written to a fresh
`tempfile` directory under the worktree's `artifacts/s2/ui_core/test-tmp/` and
removed after. No test reads a real-take WAV.

The fixture is the S1 10 s synthetic 32.703 Hz + 130.813 Hz tone run, with
synthetic layers:

- a tone-ab.json with 3 pairs of 0.5 s excerpts plus their real hashes and a
  blind key;
- a flags-triage.json with 6 flags (2 shown, 1 suppressed, 3 navigation);
- a spans file with 6 boundaries covering supported, weak and uncertain joins
  and one unit outside the source;
- phrase-timing.json with 3 measured rows and 1 abstained row;
- a detector phrases file with 3 spans.

Required tests (≥ 10; target 18):

1. `test_stage_strip_short_hashes_and_analysis_input_divergence`
2. `test_ab_blind_key_hidden_until_reveal_and_reveal_not_saved`
3. `test_ab_shows_measured_lu_delta_gains_and_preference_not_recorded`
4. `test_no_autoplay_no_play_calls_preload_none_exclusive_pause`
5. `test_trial_player_labelled_unadopted_and_optional_when_unavailable`
6. `test_coverage_uncertain_and_weak_joins_have_text_and_shape_markers`
7. `test_coverage_lanes_separate_and_summary_denominators`
8. `test_triage_default_at_most_one_per_window_navigation_and_suppressed_toggles`
9. `test_basis_badges_user_reported_intent_review_detector_distinct`
10. `test_phrase_timing_unvalidated_measurement_and_abstain_reason`
11. `test_generated_text_contains_no_verdict_words` (rendered text across all
    fixtures, against the section 5.6 list)
12. `test_quick_marks_saved_via_annotation_v2_are_accepted_by_phrase_anchor`.
    Node emits 12 requests, Python writes them through
    `annotation_v2.AnnotationStore` on a synthetic `review_server.Session`, and
    then `phrase_anchor.marks_from_annotation_store` must accept 12/12 with 0
    excluded.
13. `test_quick_mark_uncertain_save_retries_same_key_and_stale_keeps_queue`
14. `test_quick_mark_keys_ignore_typing_and_modifiers_and_never_play`
15. `test_foreign_bundle_refused_and_s1_controls_remain`
16. `test_composer_refuses_source_or_media_hash_mismatch_per_layer`
17. `test_composer_refuses_existing_or_runs_output`
18. `test_bundle_carries_unknown_fields_and_claim_boundary`

### 8.2 Real-take read-only composition (Phase 2, M)

1. Regenerate flags-triage under `artifacts/s2/ui_core/real-take/` and verify
   its denominators against the annot_corpus receipt.
2. Compose the bundle with `--trial-excerpts` (one FFmpeg job, at most 600 s
   timeout).
3. Before and after, hash the session run's `manifest.json`, `cleaned.wav`,
   `denoised.wav` and `source.wav`, and the analysis run's `flags.json`. All
   must be unchanged.
4. Real-take browser checks are read-only: no save and no annotation smoke.
   The harness refuses saves when `source_name` does not start with
   `synthetic-`.

### 8.3 Walkthrough: `review/browser_smoke_s2.py`

The walkthrough runs an owned headless Chrome on a unique temporary profile
with a muted, ephemeral loopback server. That server is an in-process subclass
that wires `practice_s2_routes` exactly as the root diff will. The harness
stops only its own PID, and only after verifying the profile argument. The
configurations are:

- 375×812 at DPR 3, mobile;
- 390×844 at DPR 3, mobile;
- desktop 1440×1000 at DPR 1;
- 200 % zoom, as 720×1000 CSS px at DPR 2.

For each configuration it records:

- `scrollWidth ≤ innerWidth` (no horizontal overflow);
- that every S2 panel is visible or shows an unavailable reason;
- a screenshot path;
- the console exception count;
- the `HTMLMediaElement.paused` state of every player after load and after all
  key actions (it must remain true).

On the synthetic fixture only, the walkthrough also enables the labelling
session, presses `B` 12 times at distinct times reached by `→`, saves, reloads,
and reads back 12 records. On the real-take bundle it renders read-only. If
Chrome is not resolvable, the receipt says
`skipped: chrome_not_found <path>` and no paint claim is made.

### 8.4 Completion metrics (frozen)

Claim classes: **M** measured, **M-syn** measured on synthetic fixtures,
**I** inference, **L** listening (operator-owned, never produced by this lane).

| # | Metric | Denominator | Class | Acceptance |
| --- | --- | --- | --- | --- |
| 1 | Lane tests passed | discovered in `test_review_ui_s2` (≥ 10) | M | all pass |
| 2 | S1 regression | 13 tests in `test_review_ui_s1` | M | 13/13 |
| 3 | Viewport configs without horizontal overflow | 4 (375, 390, 1440, 200 %) | M | 4/4, or a receipt with the skip reason |
| 4 | Players paused after load and key actions | all players × 4 configs | M | 100 % paused; 0 `play()` call sites; 0 `autoplay` attributes |
| 5 | Synthetic quick marks saved and read back | 12 queued | M-syn | 12/12, at most 2 keystrokes per mark (1 to queue + a shared save); wall time recorded, no operator-speed claim |
| 6 | Saved marks accepted by `phrase_anchor` | 12 | M-syn | 12 accepted, 0 excluded |
| 7 | Real-take triage display fidelity | `denominators.total_flags` (expected 171) | M | shown/hidden/suppressed rendered counts equal file denominators (15/112/44) |
| 8 | Real-take S2 layers available | 5 (stages, A/B, coverage, triage, timing) | M | count reported; each unavailable layer carries a reason |
| 9 | Verdict words in generated S2 text | all rendered S2 text nodes, fixtures + real take | M | 0 |
| 10 | Required unknown/claim-boundary keys present | section 7 list (21 keys) | M | 21/21 |
| 11 | Accepted inputs unchanged | 5 protected hashes | M | 5/5 equal before and after |
| 12 | Operator labelling session on the real take | — | L | not performed by lane; `unknown` |

Experimental non-improvement does not apply: this lane runs no arms. A metric
that misses acceptance is reported with its numbers and a defect note, never
hidden.

## 9. Root-owned changes to request (Phase 2 hands the exact diff)

The planned shape for `scripts/review_server.py` has four parts. Most logic
lives in the lane-owned `review/practice_s2_routes.py`, which keeps the root
diff small.

1. `serve` accepts `--practice-s2 BUNDLE_DIR` (optional). At startup the server
   calls `practice_s2_routes.load(bundle_dir, session)`. That call verifies the
   bundle binding against `session.source_hash` / `session.manifest_hash`, then
   hash-verifies and opens each media file as a `Media` (signature-checked fd).
   On refusal the server still starts, and the route answers 404 with the
   reason.
2. `GET /api/practice-s2` returns `bundle.json`, or 404
   `{"error":"practice_s2_bundle_not_configured"}`.
3. `GET /media/s2/<name>` serves hash-verified bundle media through the
   existing `send_media` (Range supported). Unknown names return 404.
4. The asset allowlist gains `/practice_s2.js`.

There is no new POST route. Labelling uses the existing
`/api/annotations-v2`. A `just` recipe line for composing and serving, and an
MCP/tool descriptor, are not requested this sprint. The composer is a review
helper, not an advertised processing tool. Root may decide otherwise.

## 10. Timebox and resource rules

There is at most one heavy job at a time: either the trial-excerpt FFmpeg job
or the headless Chrome walkthrough. Every subprocess has an explicit timeout.
Python is stdlib-only, with no pip installs. FFmpeg and FFprobe come from the
`FFMPEG`/`FFPROBE` environment variables. The lane commits with
`--no-gpg-sign`, and root signs the merge.

## 11. Phase 2 implementation notes (additive; sections 1–10 unchanged except 5.6, amended by the Phase 4 repair)

Implemented on `sprint/20261006-s2/ui_core`. These notes record choices made
inside the frozen contract and the places where Phase 2 had to resolve
ambiguity. Receipts: `docs/agent-notes/sprints/20261006-s2/ui_core-walkthrough.json`
and `ui_core-handoff.json`.

- **Per-file level lines (5.2).** Each pair's per-file static gain, excerpt
  LUFS and sample peak are rendered in a collapsed `<details>` ("gains can
  hint at the mapping"). The static gains differ by arm (−3.37 dB FULLER,
  −0.17 dB source on the real take), so showing them inline would reveal the
  blind mapping before listening. The region match line,
  `operator_preference: not recorded` and `listening acceptance: not
  established` are always visible.
- **Phrase timing binding (3, 4).** `phrase-timing.json` carries an analyzed
  input hash but no original source hash. The composer accepts a timing file
  only when its `inputs.analyzed_input_sha256` is bound to the original source
  by the session manifest outputs, the supplied detector `phrases.json`
  lineage, or a supplied phrase_anchor `grid_analyzed_input_sha256`. Otherwise
  the file is refused with `layer_source_mismatch`. Timing files are labelled
  `<run id>/phrase-timing.json` because both real files share a basename.
- **Bundle key.** `tone-ab.json`'s own `status` is copied as
  `layers.tone_ab.tone_ab_status`; `layers.tone_ab.status` is the layer
  availability. `layers.flags_triage.document` and
  `layers.phrase_timing.files[].document` hold the verbatim documents.
- **Anchor default (5.3).** The selector opens on the middle candidate (k30 of
  k29/k30/k31) so the ±1 click alternatives sit on either side. It is a view
  choice only; every row still reads `anchor review candidate · not adopted`.
- **Labelling session without a bundle.** Quick marks write only to the
  session's own v2 store, so the labelling session still works when the S2
  bundle is absent or refused. N/P and Shift+N/P then do nothing.
- **Upstream text.** Verbatim upstream strings (timing row labels, retained
  flag records, tone_ab limitations, the operator's quote) carry the class
  `s2-upstream` and are excluded from the generated-text verdict-word scan.
  The scan counts them separately.
- **Walkthrough mark positions (8.3).** The fixture's playable source span is
  2–12 s, so 1 s arrow steps reach at most 11 distinct positions. The
  walkthrough queues 11 marks at the start and after each `→`, and the twelfth
  after `P` (intent boundary 8.5 s). There are 12 `B` presses and 1 shared save.
- **Root diff file.** The exact `scripts/review_server.py` change is stored as
  `review/practice_s2_review_server.diff` (`git apply --check` clean at
  `0cdca01`). A patched copy was served once against the synthetic fixture,
  answering `/api/practice-s2` 200, `/media/s2/excerpt-1-X.wav` 206 with
  Range, an unknown name 404, and `/practice_s2.js` 200.
- **Phase 4 repair: phrase_timing schema 2 (5.6).** Main `84ee740`/`ef31930`
  withheld real-take direction. The Phase 2 page rendered `tendency_label` for
  every measured row, so the real-take bundle showed 56 direction labels
  (27 ahead_of_click, 27 within_5_ms, 2 behind_click). The repair renders
  direction only for synthetic known-offset fixture rows, refuses schema 1, and
  recomposes the real-take bundle from schema-2 timing files regenerated with
  main's `scripts/phrase_timing.py` on the same analysis and phrase inputs
  (identical offsets, 56 measured rows, 0 direction labels).
