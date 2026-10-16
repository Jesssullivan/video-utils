# Operator onset labels and the D6 onset benchmark

Status: implemented 2026-10-15 for S4 (TIN-5491, lane L5-onsets). No real labels
exist yet. The benchmark abstains until the operator's labelling session supplies at
least 10 onset labels. Synthetic tests cover the scorer; no real-take number in
this repository comes from it.

## What is measured

The benchmark asks one question: **how often does each detector place an onset
candidate where the operator heard an attack?** It joins operator onset labels to
detector onset candidates and reports precision, recall and F1 at **10, 25 and 50 ms**.

| Term | Source | Authorship |
| --- | --- | --- |
| Operator onset label | v2 store, kind `onset`, a point on the original source clock | user-authored (`operator_assertion` or `operator_context`) |
| Onset-labelled segment | v2 store, kind `onset_segment`, a known span | user-authored; asserts every audible onset inside is labelled |
| Detector onset candidate | bound `analysis.json` events whose kind ends in `_attack_candidate` | detector hypothesis |

The validator refuses an onset kind with a detector or reference basis. Detector
candidates never enter the store, so the two remain distinguishable in every
projection. Periodic click candidates (`periodic_high_frequency_candidate`) are
excluded. Each detector kind (`broadband_attack_candidate`, and with librosa the
`*_attack_candidate` families) is scored on its own and never merged. Each kind is
scored on the `source_timeline_seconds` axis and, when every event carries it, on
the synthetic-probe `delay_compensated_source_timeline_seconds` axis as a separate
row.

### Matching

Matching is one-to-one: a label matches at most one detection, and a detection
matches at most one label. Detections are matched against **every** counted
operator onset label, including labels outside declared segments and, for the
`confirmed_only` subset, the labels that are not confirmed. Among all one-to-one
matchings within the tolerance, the scorer picks the one with the most matches to
scored labels, then the most pairs overall, then the smallest total absolute
offset. It is an ordered dynamic programme
(`scripts/onset_benchmark.py: ordered_pairs`). On a line, any crossing pair can be
uncrossed without losing a match, changing which labels are matched or adding
offset, so the ordered optimum is the global optimum. Tests compare it with brute
force on random small sets, with and without scored-label priority.
Without the priority it is the same programme as `event_metrics_v2` in
`scripts/benchmark.py`. That file is not changed, because the admitted holdout
plan binds its bytes. A test checks that the two agree.

- **Tolerance boundary.** A pair matches when `|detector − operator| ≤ tolerance +
  1e-9 s`. Imported labels are rounded to 6 decimal places, so an offset of exactly
  10 ms can sit a few 1e-12 s above 0.010 in binary floating point. The epsilon
  keeps that offset inside the 10 ms window; it is far below any frame. The frozen
  `event_metrics_v2` has no epsilon.

- Offsets are `detector − operator`. A positive median means the detector is later
  than the heard attack. The median is reported but never subtracted.
- `contested_detection_count` counts detections within tolerance of two or more
  labels. `contested_label_count` counts labels with two or more detections in
  tolerance, for example flams, double attacks or a tremolo burst. These counts show
  ambiguity. They never change a match.

### Scope, precision and abstention

- **No declared segment (recall only).** Unlabelled time is unknown, not onset-free.
  Recall is matched labels ÷ labels. Precision and F1 are null with
  `no_operator_declared_fully_labelled_segment`.
- **With `onset_segment` spans.** Overlapping spans are merged. Recall counts only
  labels inside a segment; labels outside are counted and still take part in
  matching. The segment edge rule is symmetric:
  - a detection just outside the edge can match a scored label inside it, and that
    counts as a hit;
  - a detection is a false positive only if it lies inside a segment **and** is
    matched to no operator label at all. A detection inside the segment that pairs
    with a label just outside a hand-drawn edge is neither a hit nor a false
    positive; it is counted as `detections_in_scope_matched_to_unscored_labels`.

  Precision is scored matches ÷ (scored matches + false positives). Region labels
  in an audio editor are dragged by hand and often start a few ms after the first
  attack; this rule keeps that slack from lowering precision. Example at 25 ms:
  labels 1.995 s (outside) and 2.5 s, detections 2.004 s and 2.5 s, segment
  2.0–3.0 s give one scored label, one match, no false positive, precision 1.0.
- **Abstention.** With 0 scored labels the status is `no_operator_onset_labels`.
  With 1–9 it is `insufficient_operator_onset_labels`. Neither case reports a rate.
  The same rule applies to the `confirmed_only` subset, which scores only labels
  whose `operator_certainty` is `confirmed`. Unconfirmed labels still take part in
  matching, so a detection at an unconfirmed attack is never a false positive of
  that subset.
- **Counted labels.** A label counts when its actor is `operator`, its basis is
  operator-authored and its status is not `dismissed_candidate`. Quick marks save as
  `needs_review`, and they count. Excluded records are counted by reason.

### Claims boundary

Agreement is not note correctness. Every receipt carries
`note_correctness: not_assessed_no_approved_reference`,
`missed_or_extra_notes: not_assessed_no_approved_reference` and
`musical_verdict: not_established`. A missed label means the detector placed no
candidate near a heard attack. It does not mean a missed note. The operator's own
placement error, the physical capture latency and the detector delay are
uncalibrated. The stdlib detector has 5 ms frames (hop 80 at 16 kHz), so 10 ms is
the tightest meaningful tolerance. Read 10 ms results together with the median
offset.

## Outputs

- `just onset-benchmark RUN_DIR OUTPUT.json` writes a fresh receipt (schema
  `onset-label-benchmark-v1`). It refuses to overwrite. The receipt binds the
  manifest hash, the source hash, the store hash and revision, and the analysis hash
  with its lineage (`report.analysis_lineage`). It contains no paths. A store bound
  to another manifest is refused. An unbound analysis gives
  `detector_analysis_unbound`. As in `report_bundle.py`, an analysis whose
  `source_lineage.original_source_sha256` names another source is
  `rejected_original_source_mismatch` and is not scored, so the receipt and the
  bundle table agree for the same inputs.
- `scripts/report_bundle.py build` adds `tables/onset_labels.csv` (status and counts)
  and `tables/onset_benchmark.csv` (one row per detector, axis, subset and
  tolerance) to the hash-bound bundle. It also adds `run.onset_labels` to
  `bundle.json`. No free text is copied.
- `reports/demo.qmd` section 7 reads those tables. Every state with zero operator
  onset labels (no store, an unbound or refused store, or a bound store without
  onset records) prints **"No operator onset labels yet."** with the store status,
  and no scoring mode. `plot_onset_benchmark` draws an abstention panel. It shows no
  rates until the scorer measures.

## Operator guide: one labelling hour

Goal: at least 10 onset labels in a fully labelled segment, and at least 10 phrase
boundaries, on one 20–30 s stretch of the take. The times below are planning
estimates, not measurements.

| Step | Time |
| --- | ---: |
| Pick the stretch and open the tools | 5 min |
| Onsets in one or two fully labelled segments (40–100 labels) | 25–35 min |
| Phrase boundaries, at least 10 | 10 min |
| Import, check and score | 5–10 min |

**Pick the stretch.** Choose 20–30 s after the first five seconds, which hold setup
and amp sounds. Pick a passage you can still hear attack by attack, such as a riff,
chugs or a breakdown. The store holds at most 200 records. At technical tempos, a
fully labelled segment of 3–8 s inside the stretch is enough. Keep the onsets you
label below about 150.

### Onsets: label in an audio editor with a waveform (recommended)

Tapping along in real time adds your reaction time, often 150–250 ms. That is far
outside a 50 ms window. Place onsets on a waveform instead.

1. Open the run's `source.wav` in an audio editor with a label track (for example
   Audacity). Its hash is in the run manifest, and the import refuses a run whose
   manifest timeline does not declare `no_time_stretch: true`. `denoised.wav` or
   `cleaned.wav` from the same run also work if their attacks are easier to see.
2. Zoom in until single attacks are visible. Add a **point label** at the start of
   each attack you hear. Palm mutes, ghost notes, tapping and legato onsets count
   when you hear them. If you are unsure, put your words in the label text, for
   example `unsure`.
3. Add one **region label** over each span in which you labelled every onset you
   could hear. This declares an `onset_segment`, and only it enables precision. Do
   not cover parts you skipped. The edges need not be exact: a label a few ms
   outside the region still absorbs its detection (see the edge rule above).
4. Export the labels as text. Each line is `start<TAB>end<TAB>text`, in seconds from
   the start of the file.
5. Import them:

   ```sh
   just onset-import RUN_DIR LABELS.txt source.wav onset "onset" confirmed accepted_observation
   ```

   The fifth argument is the text saved for labels whose text is empty. The last
   two set every imported row's certainty (`uncertain`, the default, or
   `confirmed`) and review state (`needs_review`, the default, or
   `accepted_observation`). Only `confirmed` labels enter the `confirmed_only`
   subset, so import the labels you are sure of as `confirmed` and any doubtful
   ones from a second label file with the defaults. Times are
   moved onto the source clock: the manifest's `audio_start_seconds` plus the label
   seconds. The import checks every row before it writes anything. Running it again
   replays and does not duplicate.

### Phrase boundaries

Use either path. Each one gives `phrase_duration` point marks, which
`phrase_anchor.py score` reads.

- **Label track:** export a second label file with point labels at boundaries, then
  run `just onset-import RUN_DIR BOUNDARIES.txt source.wav phrase_duration "phrase boundary"`.
- **Browser:** run `just review RUN_DIR` and open the printed `http://127.0.0.1:…` URL.
  Tick **Labelling session (quick marks)**, type template text such as `phrase
  boundary`, then pause on each boundary and press **B**. Press **Save queued
  marks**. Pause before marking. A mark taken during playback carries your reaction
  delay.

The browser can also add onsets. Choose `onset` under **Kind for key I** and press
**I** while paused on an attack. You can declare a segment in **Report a practice
issue**: set start and end, tick **Known span**, pick **Onset-labelled segment**
and state that every onset inside is marked. The browser has no waveform, so
placing onsets this way is less precise.

### Check and score

```sh
just annotations-v2 RUN_DIR                     # counts and kinds; your words stay local
just onset-benchmark RUN_DIR artifacts/benchmarks/onsets-YYYYMMDD.json
just phrase-anchor-score SPANS.json RUN_DIR artifacts/s2/phrase_anchor_riff/score-YYYYMMDD.json
```

The onset benchmark reports `insufficient_operator_onset_labels` below 10 scored
labels. The phrase-anchor scorer abstains below 10 boundary marks
(`insufficient_operator_boundaries`). `SPANS.json` is the existing
`phrase_anchor.py spans` projection for this take (see
[PHRASES_S2](sprints/PHRASES_S2.md)). To show the result in the Quarto report,
rebuild the report bundle with the run's store.

Labels, label files and receipts made from the real take stay on the operator host.
A public receipt carries only hashes, counts and the measured rates.

## Limits

- Labels are the operator's listening judgement. Their own timing error is unknown,
  and no second labeller exists.
- One stretch of one take is a small sample, and rates carry no confidence interval.
  Read the counts next to every rate.
- Without an approved expected-rhythm reference, a missed label is never a missed
  or extra note.
- The label-track import accepts only `source.wav`, `denoised.wav` or `cleaned.wav`
  from the same run, checked against the manifest hashes, and only when the
  manifest timeline declares `no_time_stretch: true`. No other editor file or clock
  is supported. One import applies one certainty and one review state to all rows.
- The scorer has no MCP tool or skill yet. It runs through `just`, the
  `scripts/onset_benchmark.py` CLI and the report bundle.
